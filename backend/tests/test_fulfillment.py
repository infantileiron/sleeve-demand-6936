import pathlib
import sys

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.config.database import Base
from src.models.entities import (
    FulfillmentLock, Issue, Reconciliation, Requisition, Reservation, Sleeve, Stock, Usage, User, Workstation,
)
from src.schemas.business import ReconciliationInput, RequisitionInput, StockInput, StocktakeInput
from src.services import fulfillment


@pytest.fixture()
def session(tmp_path):
    engine = create_engine(f'sqlite+pysqlite:///{tmp_path / "svc.db"}', connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)
    db = Session()
    db.add_all([
        Sleeve(code='SL-A4', title='A4', pack_size=25, lead_weeks=3, substitute_code='SL-A3'),
        Sleeve(code='SL-A3', title='A3', pack_size=25, lead_weeks=3, substitute_code=None),
        Sleeve(code='SL-MAP', title='地图', pack_size=5, lead_weeks=5, substitute_code=None),
        Workstation(code='WS-1', title='照片工位'),
        Workstation(code='WS-2', title='地图工位'),
        User(email='a@x', password_hash='x:y', role='analyst'),
        FulfillmentLock(id=1),
    ])
    db.commit()
    user = db.scalar(select(User))
    db.add(Stock(sleeve_code='SL-A4', on_hand=10))
    db.add(Stock(sleeve_code='SL-A3', on_hand=10))
    db.add(Stock(sleeve_code='SL-MAP', on_hand=3))
    db.commit()
    yield db, user
    db.close()
    engine.dispose()


def order(**kwargs):
    base = {'workstation_code': 'WS-1', 'week': '2026-10-19', 'request_key': 'key-0001'}
    base.update(kwargs)
    return RequisitionInput(**base)


def test_submit_reserves_and_reports_gap(session):
    db, user = session
    view = fulfillment.submit_requisition(db, order(lines=[{'sleeve_code': 'SL-MAP', 'units': 5}]), user)
    assert view['status'] == 'short'
    assert view['lines'][0]['reserved_units'] == 3
    assert view['lines'][0]['shortage_units'] == 2


def test_idempotent_retry_returns_same_order(session):
    db, user = session
    data = order(lines=[{'sleeve_code': 'SL-MAP', 'units': 4}])
    first = fulfillment.submit_requisition(db, data, user)
    second = fulfillment.submit_requisition(db, data, user)
    assert first['id'] == second['id']
    assert db.scalar(select(Reservation).where(Reservation.requisition_id == first['id']))
    assert len(list(db.scalars(select(Requisition)))) == 1


def test_duplicate_key_different_payload_rejected(session):
    db, user = session
    fulfillment.submit_requisition(db, order(lines=[{'sleeve_code': 'SL-MAP', 'units': 3}]), user)
    with pytest.raises(Exception):
        fulfillment.submit_requisition(db, order(lines=[{'sleeve_code': 'SL-MAP', 'units': 4}]), user)


def test_no_oversell_between_orders(session):
    db, user = session
    fulfillment.submit_requisition(db, order(week='2026-10-19', request_key='key-aaaa',
                                             lines=[{'sleeve_code': 'SL-MAP', 'units': 3}]), user)
    second = fulfillment.submit_requisition(db, order(week='2026-10-19', request_key='key-bbbb',
                                                      lines=[{'sleeve_code': 'SL-MAP', 'units': 3}]), user)
    assert second['status'] == 'short'
    assert second['lines'][0]['reserved_units'] == 0


def test_stocktake_replans_unissued_but_keeps_issued(session):
    db, user = session
    view = fulfillment.submit_requisition(db, order(lines=[{'sleeve_code': 'SL-A4', 'units': 4}]), user)
    issued = fulfillment.issue_requisition(db, view['id'], user)
    assert issued['lines'][0]['issued_units'] == 4
    assert issued['status'] == 'issued'
    before = db.get(Stock, 'SL-A4').on_hand
    assert before == 6
    # 盘点发现只剩 1，已发的 4 张不挪。
    fulfillment.stocktake(db, StocktakeInput(sleeve_code='SL-A4', counted_units=1, note='盘点'), user)
    assert db.get(Stock, 'SL-A4').on_hand == 1
    again = fulfillment.get_requisition(db, view['id'])
    assert again['lines'][0]['issued_units'] == 4


def test_old_order_queries_current_claimable_after_stocktake(session):
    db, user = session
    view = fulfillment.submit_requisition(db, order(lines=[{'sleeve_code': 'SL-MAP', 'units': 5}]), user)
    assert view['status'] == 'short'
    # 补料后重排，旧单可查到现在能领什么。
    fulfillment.receive_stock(db, StockInput(sleeve_code='SL-MAP', units=10), user)
    refreshed = fulfillment.get_requisition(db, view['id'])
    assert refreshed['status'] == 'ready'
    assert refreshed['lines'][0]['reserved_units'] == 5


def test_issue_twice_is_idempotent(session):
    db, user = session
    view = fulfillment.submit_requisition(db, order(lines=[{'sleeve_code': 'SL-A4', 'units': 4}]), user)
    first = fulfillment.issue_requisition(db, view['id'], user)
    second = fulfillment.issue_requisition(db, view['id'], user)
    assert first['lines'][0]['issued_units'] == second['lines'][0]['issued_units'] == 4
    assert db.get(Stock, 'SL-A4').on_hand == 6


def test_reconcile_merges_issue_into_weekly_usage(session):
    db, user = session
    v1 = fulfillment.submit_requisition(db, order(week='2026-10-26', request_key='key-one-1',
                                                  lines=[{'sleeve_code': 'SL-A4', 'units': 2}]), user)
    v2 = fulfillment.submit_requisition(db, order(workstation_code='WS-2', week='2026-10-26',
                                                  request_key='key-two-2',
                                                  lines=[{'sleeve_code': 'SL-A4', 'units': 3}]), user)
    fulfillment.issue_requisition(db, v1['id'], user)
    fulfillment.issue_requisition(db, v2['id'], user)
    # 未核清前该周保持缺传。
    row = db.scalar(select(Usage).where(Usage.sleeve_code == 'SL-A4', Usage.week == '2026-10-26'))
    assert row.state == 'missing'
    result = fulfillment.reconcile_week(db, ReconciliationInput(week='2026-10-26', note='核清'), user)
    merged = {item['sleeve_code']: item['units'] for item in result['usage']}
    assert merged['SL-A4'] == 5
    row = db.scalar(select(Usage).where(Usage.sleeve_code == 'SL-A4', Usage.week == '2026-10-26'))
    assert (row.state, row.units) == ('observed', 5)


def test_issued_material_cannot_be_changed_by_replan(session):
    db, user = session
    view = fulfillment.submit_requisition(db, order(lines=[{'sleeve_code': 'SL-A3', 'units': 5}]), user)
    # SL-A4 可代用 SL-A3，但原规格充足时先用原规格。
    assert view['lines'][0]['allocation'] == [{'sleeve_code': 'SL-A3', 'units': 5}]
    fulfillment.issue_requisition(db, view['id'], user)
    assert db.get(Stock, 'SL-A3').on_hand == 5
    assert db.get(Stock, 'SL-A4').on_hand == 10
    assert db.scalar(select(Issue).where(Issue.requisition_id == view['id'])).units == 5
