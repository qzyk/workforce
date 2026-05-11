"""
Integration tests pentru rutele Faza 6 (IoT / Digital Twin).
"""

import json
import pytest

from models import (db, Senzor, SensorReading, SensorAlert,
                    ElementBIM, Cladire, Santier)
from services import feature_flags as ff
from services import iot_ingest


@pytest.fixture
def element(app):
    with app.app_context():
        s = Santier(cod='S-INT6', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        el = ElementBIM(cladire_id=c.id, cod='E1', tip_element='wall',
                        status='construit', nume='W')
        db.session.add(el); db.session.commit()
        yield el.id


def test_sensors_lista_redirects_when_flag_off(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-iot-sensors', False)
    resp = authenticated_client.get('/bim/sensors', follow_redirects=False)
    assert resp.status_code == 302


def test_sensors_lista_renders_when_flag_on(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-iot-sensors', True)
    resp = authenticated_client.get('/bim/sensors')
    assert resp.status_code == 200


def test_create_sensor_via_route(authenticated_client, app, element):
    with app.app_context():
        ff.set_flag('bim-iot-sensors', True)
        Senzor.query.delete(); db.session.commit()

    resp = authenticated_client.post('/bim/sensor/nou', data={
        'cod': 'TEMP-INT', 'nume': 'Test temperature', 'tip': 'temperatura',
        'unitate': '°C', 'element_bim_id': element,
        'threshold_min': '18', 'threshold_max': '26',
    }, follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        s = Senzor.query.filter_by(cod='TEMP-INT').first()
        assert s is not None
        assert s.api_key is not None


# ====================================================
# Ingest API (token auth)
# ====================================================

def test_ingest_api_requires_flag(client, app, element):
    with app.app_context():
        ff.set_flag('bim-iot-sensors', False)
    resp = client.post('/bim/api/sensors/ingest', json={'valoare': 22.5})
    assert resp.status_code == 403


def test_ingest_api_requires_token(client, app, element):
    with app.app_context():
        ff.set_flag('bim-iot-sensors', True)
    resp = client.post('/bim/api/sensors/ingest', json={'valoare': 22.5})
    assert resp.status_code == 401


def test_ingest_api_invalid_token(client, app, element):
    with app.app_context():
        ff.set_flag('bim-iot-sensors', True)
    resp = client.post('/bim/api/sensors/ingest',
                        json={'valoare': 22.5},
                        headers={'X-Sensor-Token': 'xxxxxxxxxxxxxxxxxxx'})
    assert resp.status_code == 401


def test_ingest_api_success(client, app, element, admin_user):
    with app.app_context():
        ff.set_flag('bim-iot-sensors', True)
        s = iot_ingest.create_senzor('ING-API-1', 'X', 'temperatura',
                                       element_bim_id=element,
                                       threshold_min=18, threshold_max=26,
                                       user=admin_user)
        token = s.api_key
        sid = s.id

    # Send valoare normala (no alert)
    resp = client.post('/bim/api/sensors/ingest',
                        json={'valoare': 22.5},
                        headers={'X-Sensor-Token': token})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['alert_created'] is False
    assert data['threshold_violated'] is None

    with app.app_context():
        assert SensorReading.query.filter_by(senzor_id=sid).count() == 1


def test_ingest_api_creates_alert_when_above_max(client, app, element, admin_user):
    with app.app_context():
        ff.set_flag('bim-iot-sensors', True)
        s = iot_ingest.create_senzor('ING-API-2', 'X', 'temperatura',
                                       element_bim_id=element,
                                       threshold_max=20, user=admin_user)
        token = s.api_key

    resp = client.post('/bim/api/sensors/ingest',
                        json={'valoare': 35.0},
                        headers={'X-Sensor-Token': token})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['alert_created'] is True
    assert data['threshold_violated'] == 'peste_max'


def test_ingest_api_with_explicit_ts(client, app, element, admin_user):
    with app.app_context():
        ff.set_flag('bim-iot-sensors', True)
        s = iot_ingest.create_senzor('ING-API-3', 'X', 'temperatura',
                                       element_bim_id=element, user=admin_user)
        token = s.api_key

    resp = client.post('/bim/api/sensors/ingest',
                        json={'valoare': 22.5, 'ts': '2026-05-10T12:34:56'},
                        headers={'X-Sensor-Token': token})
    assert resp.status_code == 200


def test_ingest_api_missing_valoare(client, app, element, admin_user):
    with app.app_context():
        ff.set_flag('bim-iot-sensors', True)
        s = iot_ingest.create_senzor('ING-API-4', 'X', 'temperatura',
                                       element_bim_id=element, user=admin_user)
        token = s.api_key
    resp = client.post('/bim/api/sensors/ingest', json={},
                        headers={'X-Sensor-Token': token})
    assert resp.status_code == 400


# ====================================================
# API state + history
# ====================================================

def test_api_element_state(authenticated_client, app, element, admin_user):
    with app.app_context():
        ff.set_flag('bim-iot-sensors', True)
        s = iot_ingest.create_senzor('STATE-1', 'X', 'temperatura',
                                       element_bim_id=element, user=admin_user)
        iot_ingest.ingest_reading(s, 23.5)

    resp = authenticated_client.get(f'/bim/api/element/{element}/state')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['enabled'] is True
    assert data['count_sensors'] == 1
    assert data['sensors'][0]['ultima_valoare'] == 23.5


def test_api_sensor_history(authenticated_client, app, element, admin_user):
    with app.app_context():
        ff.set_flag('bim-iot-sensors', True)
        s = iot_ingest.create_senzor('HIST-1', 'X', 'temperatura',
                                       element_bim_id=element, user=admin_user)
        from datetime import datetime, timedelta
        base = datetime.utcnow() - timedelta(hours=2)
        for i in range(3):
            iot_ingest.ingest_reading(s, 20 + i, ts=base + timedelta(minutes=i*10))
        sid = s.id

    resp = authenticated_client.get(f'/bim/api/sensor/{sid}/history?agg=raw')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['enabled'] is True
    assert data['count'] == 3
