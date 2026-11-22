"""并发提交不得超发；同一提交编号重试不得重复扣减。

进程内由全局可重入锁串行化，跨进程由 MySQL 单行 FOR UPDATE 串行化（READ COMMITTED）。
这里用多线程 + 独立会话覆盖进程内的串行化路径。
"""

import pathlib
import sys
import threading

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.config.database import Base
from src.models.entities import (
    FulfillmentLock, Issue, Reservation, Requisition, Sleeve, Stock, User, Workstation,
)
from src.schemas.business import RequisitionInput
from src.services import fulfillment


@pytest.fixture()
def factory(tmp_path):
    engine = create_engine(f'sqlite+pysqlite:///{tmp_path / "concurrent.db"}',
                           connect_args={'check_same_thread': False, 'timeout': 30})
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)
    with Session() as db:
        db.add_all([
            Sleeve(code='SL-MAP', title='地图', pack_size=5, lead_weeks=5),
            Workstation(code='WS-1', title='照片工位'),
            Workstation(code='WS-2', title='地图工位'),
            User(email='a@x', password_hash='x:y', role='analyst'),
            Stock(sleeve_code='SL-MAP', on_hand=4),
            FulfillmentLock(id=1),
        ])
        db.commit()
    yield Session
    engine.dispose()


def bearer(db):
    return db.scalar(select(User))


def run_concurrently(Session, count, payload_for):
    barrier = threading.Barrier(count)
    results = [None] * count

    def work(index):
        with Session() as db:
            user = bearer(db)
            barrier.wait()
            results[index] = fulfillment.submit_requisition(db, payload_for(index), user)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def test_concurrent_submissions_do_not_oversell(factory):
    Session = factory

    def payload(index):
        return RequisitionInput(workstation_code=['WS-1', 'WS-2'][index % 2], week='2026-10-19',
                                request_key=f'race-key-{index:03d}',
                                lines=[{'sleeve_code': 'SL-MAP', 'units': 3}])

    results = run_concurrently(Session, 2, payload)
    with Session() as db:
        reserved = db.scalar(select(func.coalesce(func.sum(Reservation.units), 0))) or 0
        stock = db.get(Stock, 'SL-MAP').on_hand
    # 两单各要 3，库存只有 4；占用总数不得超过库存，至多一张整单领齐。
    assert reserved <= stock == 4
    whole = [item for item in results if item['status'] == 'ready']
    assert len(whole) == 1


def test_concurrent_retry_of_same_key_is_idempotent(factory):
    Session = factory

    def payload(index):
        return RequisitionInput(workstation_code='WS-1', week='2026-10-19', request_key='same-key-0001',
                                lines=[{'sleeve_code': 'SL-MAP', 'units': 2}])

    results = run_concurrently(Session, 4, payload)
    ids = {item['id'] for item in results}
    assert len(ids) == 1
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Requisition)) == 1
        assert db.scalar(select(func.coalesce(func.sum(Reservation.units), 0))) == 2


def test_issue_is_idempotent_under_concurrency(factory):
    Session = factory
    with Session() as db:
        user = bearer(db)
        order = fulfillment.submit_requisition(
            db, RequisitionInput(workstation_code='WS-1', week='2026-10-19', request_key='issue-key-0001',
                                 lines=[{'sleeve_code': 'SL-MAP', 'units': 3}]), user)
        order_id = order['id']

    barrier = threading.Barrier(3)

    def work():
        with Session() as db:
            barrier.wait()
            fulfillment.issue_requisition(db, order_id, bearer(db))

    threads = [threading.Thread(target=work) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    with Session() as db:
        assert db.get(Stock, 'SL-MAP').on_hand == 1
        assert db.scalar(select(func.coalesce(func.sum(Issue.units), 0))) == 3
