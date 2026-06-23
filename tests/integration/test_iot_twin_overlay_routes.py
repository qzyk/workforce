"""
Integration tests pentru rutele Digital Twin overlay (iot-4):
- /bim/api/model/<id>/twin-overlay
- /bim/api/santier/<id>/twin-overlay
- /bim/api/sensor/<id>/current
- /bim/api/sensors/alerts/stream (SSE filtrat)

Gate dublu: bim-iot-sensors + iot-twin-overlay. Cu oricare OFF -> dezactivat
(zero regresie: viewer-ul nu coloreaza nimic).
"""

import os
import pytest

from models import db, ModelBIM, Santier, Cladire, ElementBIM
from services import feature_flags as ff
from services import iot_ingest


@pytest.fixture
def model_cu_element(app):
    """ModelBIM IFC + santier/cladire + element cu GUID, legat de model."""
    with app.app_context():
        s = Santier(cod='S-TWINR', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()

        upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'ifc')
        os.makedirs(upload_dir, exist_ok=True)
        path = os.path.join(upload_dir, 'twin_overlay_test.ifc')
        with open(path, 'w') as f:
            f.write('ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n')
        m = ModelBIM(nume='Twin Model', tip='ifc', santier_id=s.id,
                     fisier_path=os.path.relpath(path, app.root_path),
                     fisier_marime=os.path.getsize(path))
        db.session.add(m); db.session.flush()
        el = ElementBIM(cladire_id=c.id, model_bim_id=m.id, cod='E-1',
                        tip_element='wall', nume='W', ifc_global_id='GUID-1')
        db.session.add(el); db.session.commit()
        yield {'model_id': m.id, 'santier_id': s.id, 'element_id': el.id, 'path': path}
        try:
            os.unlink(path)
        except OSError:
            pass


def _set(app, sensors, overlay):
    with app.app_context():
        ff.set_flag('bim-iot-sensors', sensors)
        ff.set_flag('iot-twin-overlay', overlay)


# ---------- gating ----------

def test_overlay_dezactivat_fara_flag_overlay(authenticated_client, app, model_cu_element):
    """bim-iot-sensors ON dar iot-twin-overlay OFF -> enabled False."""
    _set(app, True, False)
    resp = authenticated_client.get(f"/bim/api/model/{model_cu_element['model_id']}/twin-overlay")
    assert resp.status_code == 200
    assert resp.get_json()['enabled'] is False


def test_overlay_dezactivat_fara_flag_sensors(authenticated_client, app, model_cu_element):
    """iot-twin-overlay ON dar bim-iot-sensors OFF -> enabled False."""
    _set(app, False, True)
    resp = authenticated_client.get(f"/bim/api/model/{model_cu_element['model_id']}/twin-overlay")
    assert resp.status_code == 200
    assert resp.get_json()['enabled'] is False


# ---------- overlay pe model: valori ----------

def test_model_overlay_fara_senzori(authenticated_client, app, model_cu_element):
    """Ambele flag-uri ON, fara senzori -> enabled True, by_guid gol (degradare)."""
    _set(app, True, True)
    resp = authenticated_client.get(f"/bim/api/model/{model_cu_element['model_id']}/twin-overlay")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['enabled'] is True
    assert data['by_guid'] == {}
    assert data['count_elemente'] == 0


def test_model_overlay_cu_alarma(authenticated_client, app, model_cu_element, admin_user):
    """Senzor peste max -> element in alarma, indexat pe GUID, cu valoarea exacta."""
    _set(app, True, True)
    with app.app_context():
        s = iot_ingest.create_senzor('OVL-1', 'Temp', 'temperatura',
                                     element_bim_id=model_cu_element['element_id'],
                                     threshold_max=25, user=admin_user)
        iot_ingest.ingest_reading(s, 40.0)

    resp = authenticated_client.get(f"/bim/api/model/{model_cu_element['model_id']}/twin-overlay")
    data = resp.get_json()
    assert data['enabled'] is True
    assert data['count_elemente'] == 1
    assert data['count_alarming'] == 1
    assert 'GUID-1' in data['by_guid']
    bucket = data['by_guid']['GUID-1']
    assert bucket['is_alarming'] is True
    assert bucket['sensors'][0]['ultima_valoare'] == 40.0


def test_santier_overlay_cu_alarma(authenticated_client, app, model_cu_element, admin_user):
    """Overlay pe santier (federat) agrega elementele cladirilor santierului."""
    _set(app, True, True)
    with app.app_context():
        s = iot_ingest.create_senzor('OVL-S', 'CO2', 'co2',
                                     element_bim_id=model_cu_element['element_id'],
                                     threshold_max=1000, user=admin_user)
        iot_ingest.ingest_reading(s, 1800.0)

    resp = authenticated_client.get(f"/bim/api/santier/{model_cu_element['santier_id']}/twin-overlay")
    data = resp.get_json()
    assert data['enabled'] is True
    assert data['count_alarming'] == 1
    assert data['by_guid']['GUID-1']['is_alarming'] is True


# ---------- /api/sensor/<id>/current ----------

def test_sensor_current_off(authenticated_client, app, model_cu_element, admin_user):
    with app.app_context():
        ff.set_flag('bim-iot-sensors', False)
        s = iot_ingest.create_senzor('CUR-OFF', 'X', 'temperatura',
                                     element_bim_id=model_cu_element['element_id'],
                                     user=admin_user)
        sid = s.id
    resp = authenticated_client.get(f'/bim/api/sensor/{sid}/current')
    assert resp.status_code == 200
    assert resp.get_json()['enabled'] is False


def test_sensor_current_valori(authenticated_client, app, model_cu_element, admin_user):
    with app.app_context():
        ff.set_flag('bim-iot-sensors', True)
        s = iot_ingest.create_senzor('CUR-1', 'X', 'temperatura',
                                     element_bim_id=model_cu_element['element_id'],
                                     threshold_max=25, user=admin_user)
        iot_ingest.ingest_reading(s, 30.0)
        sid = s.id
    resp = authenticated_client.get(f'/bim/api/sensor/{sid}/current')
    data = resp.get_json()
    assert data['enabled'] is True
    assert data['ultima_valoare'] == 30.0
    assert data['is_alarming'] is True
    assert data['alerte_noi'] >= 1


# ---------- SSE stream gating ----------

def test_sensor_alerts_stream_403_cu_flag_off(authenticated_client, app, model_cu_element):
    _set(app, True, False)
    resp = authenticated_client.get('/bim/api/sensors/alerts/stream')
    assert resp.status_code == 403


def test_sensor_alerts_stream_content_type_cu_flag_on(authenticated_client, app, model_cu_element):
    """Cu ambele flag-uri ON: stream SSE (text/event-stream). Nu consumam corpul."""
    _set(app, True, True)
    resp = authenticated_client.get('/bim/api/sensors/alerts/stream?since=0', buffered=False)
    assert resp.status_code == 200
    assert 'text/event-stream' in resp.headers.get('Content-Type', '')
    resp.close()
