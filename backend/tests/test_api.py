import os
import pathlib
import sys

import pytest
from sqlalchemy import select

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.config.database import Base, Session, engine
from src.constants.enums import Role
from src.models.entities import FulfillmentLock, Sleeve, Stock, User, Workstation
from src.utils.security import password_hash


@pytest.fixture(scope='module')
def client():
    from fastapi.testclient import TestClient

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session() as db:
        db.add_all([
            User(email='analyst@test', password_hash=password_hash('pw'), role=Role.ANALYST),
            User(email='viewer@test', password_hash=password_hash('pw'), role=Role.VIEWER),
            User(email='manager@test', password_hash=password_hash('pw'), role=Role.MANAGER),
            Sleeve(code='SL-A4', title='A4', pack_size=25, lead_weeks=3, substitute_code='SL-A3'),
            Sleeve(code='SL-A3', title='A3', pack_size=25, lead_weeks=3),
            Sleeve(code='SL-MAP', title='地图', pack_size=5, lead_weeks=5),
            Workstation(code='WS-1', title='照片工位'),
            Stock(sleeve_code='SL-A4', on_hand=10),
            Stock(sleeve_code='SL-A3', on_hand=4),
            Stock(sleeve_code='SL-MAP', on_hand=2),
            FulfillmentLock(id=1),
        ])
        db.commit()
    from src.main import app
    with TestClient(app) as test_client:
        yield test_client


def auth(client, email='analyst@test'):
    token = client.post('/api/auth/login', json={'email': email, 'password': 'pw'}).json()['token']
    return {'Authorization': f'Bearer {token}'}


def submit(client, key, lines, week='2026-10-19', ws='WS-1'):
    response = client.post('/api/requisitions', headers=auth(client),
                           json={'workstation_code': ws, 'week': week, 'request_key': key, 'lines': lines})
    assert response.status_code == 201, response.text
    return response.json()


def test_viewer_cannot_write(client):
    response = client.post('/api/requisitions', headers=auth(client, 'viewer@test'),
                           json={'workstation_code': 'WS-1', 'week': '2026-10-19',
                                 'lines': [{'sleeve_code': 'SL-MAP', 'units': 1}]})
    assert response.status_code == 403


def test_submit_and_idempotent_retry(client):
    payload = {'workstation_code': 'WS-1', 'week': '2026-10-19', 'request_key': 'retry-key-01',
               'lines': [{'sleeve_code': 'SL-MAP', 'units': 2}]}
    first = client.post('/api/requisitions', headers=auth(client), json=payload)
    second = client.post('/api/requisitions', headers=auth(client), json=payload)
    assert first.status_code == second.status_code == 201
    assert first.json()['id'] == second.json()['id']
    assert first.json()['status'] == 'ready'


def test_shortage_reported(client):
    order = submit(client, 'short-key-01', [{'sleeve_code': 'SL-MAP', 'units': 10}])
    assert order['status'] == 'short'
    assert order['totals']['shortage_units'] > 0
    assert order['totals']['shortage_units'] > order['totals']['reserved_units']


def test_issue_then_old_order_lookup(client):
    order = submit(client, 'issue-key-01', [{'sleeve_code': 'SL-A4', 'units': 6}])
    issued = client.post(f"/api/requisitions/{order['id']}/issue", headers=auth(client)).json()
    assert issued['totals']['issued_units'] == 6
    assert issued['status'] == 'issued'
    lookup = client.get(f"/api/requisitions/{order['id']}", headers=auth(client)).json()
    assert lookup['totals']['issued_units'] == 6


def test_reconcile_and_missing_week(client):
    # 未核清前实发周记为缺传。
    submit(client, 'rec-key-0001', [{'sleeve_code': 'SL-A3', 'units': 2}], week='2026-11-02')
    order = submit(client, 'rec-key-0002', [{'sleeve_code': 'SL-A3', 'units': 2}], week='2026-11-02')
    client.post(f"/api/requisitions/{order['id']}/issue", headers=auth(client))
    usage = client.get('/api/usage?sleeve_code=SL-A3', headers=auth(client)).json()
    row = next(item for item in usage if item['week'] == '2026-11-02')
    assert row['state'] == 'missing'
    reconciled = client.post('/api/weeks/reconcile', headers=auth(client, 'manager@test'),
                             json={'week': '2026-11-02', 'note': '核清'})
    assert reconciled.status_code == 201, reconciled.text
    usage = client.get('/api/usage?sleeve_code=SL-A3', headers=auth(client)).json()
    row = next(item for item in usage if item['week'] == '2026-11-02')
    assert (row['state'], row['units']) == ('observed', 2)


def test_fulfillment_view_lists_workstation(client):
    view = client.get('/api/fulfillment', headers=auth(client)).json()
    assert any(item['workstation_code'] == 'WS-1' for item in view['requisitions'])
    assert view['stock']
