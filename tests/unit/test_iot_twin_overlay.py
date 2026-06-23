"""
Teste unit pentru Digital Twin overlay (iot-4):
- services.iot_query.overlay_state_elemente (indexare pe GUID + is_alarming)
- services.realtime.get_events_since cu filtru event_types
"""

from datetime import datetime
import pytest

from models import (db, Senzor, ElementBIM, Cladire, Santier, Utilizator,
                    RealtimeEvent)
from services import iot_ingest, iot_query, realtime


@pytest.fixture
def admin(app):
    with app.app_context():
        u = Utilizator.query.filter_by(email='twin_admin@test.local').first()
        if not u:
            u = Utilizator(nume='Twin', prenume='X', email='twin_admin@test.local',
                           rol='admin', activ=True)
            u.set_password('x'); db.session.add(u); db.session.commit()
        yield u


@pytest.fixture
def setup(app, admin):
    """Doua elemente cu GUID IFC + un al treilea FARA GUID (ne-mapabil)."""
    with app.app_context():
        s = Santier(cod='S-TWIN', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        el_a = ElementBIM(cladire_id=c.id, cod='E-A', tip_element='wall', nume='A',
                          ifc_global_id='GUID-A')
        el_b = ElementBIM(cladire_id=c.id, cod='E-B', tip_element='door', nume='B',
                          ifc_global_id='GUID-B')
        el_c = ElementBIM(cladire_id=c.id, cod='E-C', tip_element='slab', nume='C',
                          ifc_global_id=None)  # fara GUID
        db.session.add_all([el_a, el_b, el_c]); db.session.commit()
        yield {'santier_id': s.id, 'a': el_a.id, 'b': el_b.id, 'c': el_c.id}


def test_overlay_gol_fara_senzori(app, setup):
    with app.app_context():
        out = iot_query.overlay_state_elemente([setup['a'], setup['b']])
        assert out['by_guid'] == {}
        assert out['count_elemente'] == 0
        assert out['count_alarming'] == 0


def test_overlay_empty_input(app):
    with app.app_context():
        out = iot_query.overlay_state_elemente([])
        assert out == {'by_guid': {}, 'count_elemente': 0, 'count_alarming': 0}


def test_overlay_indexeaza_pe_guid_si_valoare(app, setup, admin):
    """Senzor cu citire in interval -> apare, NU e in alarma, valoarea exacta."""
    with app.app_context():
        s = iot_ingest.create_senzor('T-A', 'Temp', 'temperatura',
                                     element_bim_id=setup['a'],
                                     threshold_min=18, threshold_max=26, user=admin)
        iot_ingest.ingest_reading(s, 22.5)
        out = iot_query.overlay_state_elemente([setup['a'], setup['b']])

        assert out['count_elemente'] == 1
        assert out['count_alarming'] == 0
        assert 'GUID-A' in out['by_guid']
        bucket = out['by_guid']['GUID-A']
        assert bucket['element_bim_id'] == setup['a']
        assert bucket['cod'] == 'E-A'
        assert bucket['is_alarming'] is False
        assert len(bucket['sensors']) == 1
        assert bucket['sensors'][0]['ultima_valoare'] == 22.5
        assert bucket['sensors'][0]['unitate'] == '°C'


def test_overlay_marcheaza_alarma_peste_max(app, setup, admin):
    """Citire peste threshold_max -> is_alarming True pe element + count_alarming."""
    with app.app_context():
        s = iot_ingest.create_senzor('T-B', 'Temp', 'temperatura',
                                     element_bim_id=setup['b'],
                                     threshold_max=20, user=admin)
        iot_ingest.ingest_reading(s, 35.0)
        out = iot_query.overlay_state_elemente([setup['a'], setup['b']])

        assert out['count_elemente'] == 1
        assert out['count_alarming'] == 1
        assert out['by_guid']['GUID-B']['is_alarming'] is True
        assert out['by_guid']['GUID-B']['sensors'][0]['ultima_valoare'] == 35.0


def test_overlay_un_senzor_in_alarma_marcheaza_elementul(app, setup, admin):
    """Element cu 2 senzori: daca UNUL e in alarma, elementul e in alarma."""
    with app.app_context():
        s1 = iot_ingest.create_senzor('M-1', 'Temp', 'temperatura',
                                      element_bim_id=setup['a'],
                                      threshold_max=26, user=admin)
        s2 = iot_ingest.create_senzor('M-2', 'CO2', 'co2',
                                      element_bim_id=setup['a'],
                                      threshold_max=1000, user=admin)
        iot_ingest.ingest_reading(s1, 21.0)     # OK
        iot_ingest.ingest_reading(s2, 1500.0)   # alarma
        out = iot_query.overlay_state_elemente([setup['a']])

        assert out['count_alarming'] == 1
        bucket = out['by_guid']['GUID-A']
        assert bucket['is_alarming'] is True
        assert len(bucket['sensors']) == 2


def test_overlay_sare_element_fara_guid(app, setup, admin):
    """Senzor pe element fara ifc_global_id -> sarit (ne-mapabil pe entitate 3D)."""
    with app.app_context():
        s = iot_ingest.create_senzor('NOGUID', 'X', 'temperatura',
                                     element_bim_id=setup['c'],
                                     threshold_max=10, user=admin)
        iot_ingest.ingest_reading(s, 99.0)  # ar fi in alarma, dar fara GUID
        out = iot_query.overlay_state_elemente([setup['c']])
        assert out['by_guid'] == {}
        assert out['count_elemente'] == 0
        assert out['count_alarming'] == 0


# ====================================================
# realtime.get_events_since cu filtru event_types
# ====================================================

def test_get_events_since_filtreaza_pe_tip(app):
    """event_types=['sensor_alert'] intoarce DOAR sensor_alert."""
    with app.app_context():
        RealtimeEvent.query.delete(); db.session.commit()
        realtime.publish_event('comment_new', payload={'x': 1})
        ev_alert = realtime.publish_event('sensor_alert', payload={'senzor_id': 7})
        realtime.publish_event('issue_status_change', payload={'y': 2})

        toate = realtime.get_events_since(0)
        assert len(toate) == 3  # fara filtru, backward compatible

        doar_alerte = realtime.get_events_since(0, event_types=['sensor_alert'])
        assert len(doar_alerte) == 1
        assert doar_alerte[0].id == ev_alert.id
        assert doar_alerte[0].event_type == 'sensor_alert'
