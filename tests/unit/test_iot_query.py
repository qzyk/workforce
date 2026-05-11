"""
Teste unit pentru services.iot_query.
"""

from datetime import datetime, timedelta
import pytest

from models import (db, Senzor, SensorReading, ElementBIM, Cladire, Santier,
                    Spatiu, Nivel, Utilizator)
from services import iot_ingest, iot_query


@pytest.fixture
def admin(app):
    with app.app_context():
        u = Utilizator.query.filter_by(email='iotq_admin@test.local').first()
        if not u:
            u = Utilizator(nume='IoTQ', prenume='X', email='iotq_admin@test.local',
                           rol='admin', activ=True)
            u.set_password('x'); db.session.add(u); db.session.commit()
        yield u


@pytest.fixture
def setup(app, admin):
    with app.app_context():
        s = Santier(cod='S-IQ', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        n = Nivel(cladire_id=c.id, cod='N1', nume='Parter', elevatie_m=0)
        db.session.add(n); db.session.flush()
        sp = Spatiu(nivel_id=n.id, cod='SP1', nume='Sala', tip_spatiu='room')
        db.session.add(sp); db.session.flush()
        el = ElementBIM(cladire_id=c.id, cod='E1', tip_element='wall',
                        status='construit', nume='W')
        db.session.add(el); db.session.commit()
        yield {'el_id': el.id, 'sp_id': sp.id, 'c_id': c.id}


def test_current_state_element_empty(app, setup):
    with app.app_context():
        state = iot_query.get_current_state_element(setup['el_id'])
        assert state['count_sensors'] == 0
        assert state['sensors'] == []


def test_current_state_element_with_readings(app, setup, admin):
    with app.app_context():
        s = iot_ingest.create_senzor('S-1', 'Temp', 'temperatura',
                                       element_bim_id=setup['el_id'], user=admin)
        iot_ingest.ingest_reading(s, 22.5)
        state = iot_query.get_current_state_element(setup['el_id'])
        assert state['count_sensors'] == 1
        assert state['sensors'][0]['ultima_valoare'] == 22.5
        assert state['sensors'][0]['is_alarming'] is False


def test_current_state_spatiu(app, setup, admin):
    with app.app_context():
        s = iot_ingest.create_senzor('SP-1', 'X', 'co2',
                                       spatiu_id=setup['sp_id'], user=admin)
        iot_ingest.ingest_reading(s, 800)
        state = iot_query.get_current_state_spatiu(setup['sp_id'])
        assert state['count_sensors'] == 1


def test_current_state_cladire_includes_spatiu_sensors(app, setup, admin):
    """Senzorii pe spatiile dintr-o cladire apar la cladire."""
    with app.app_context():
        # Senzor pe spatiu (din cladire)
        s1 = iot_ingest.create_senzor('SP-A', 'X', 'co2',
                                        spatiu_id=setup['sp_id'], user=admin)
        # Senzor direct pe cladire
        s2 = iot_ingest.create_senzor('CL-A', 'X', 'energie',
                                        cladire_id=setup['c_id'], user=admin)
        state = iot_query.get_current_state_cladire(setup['c_id'])
        assert state['count_sensors'] == 2


# ====================================================
# History
# ====================================================

def test_history_raw_returns_data(app, setup, admin):
    with app.app_context():
        s = iot_ingest.create_senzor('H-1', 'X', 'temperatura',
                                       element_bim_id=setup['el_id'], user=admin)
        base = datetime.utcnow() - timedelta(hours=2)
        for i in range(5):
            iot_ingest.ingest_reading(s, 20 + i, ts=base + timedelta(minutes=i*10))
        hist = iot_query.get_history(s.id, agg='raw')
        assert hist['count'] == 5
        # Sortate ascendent
        assert hist['data'][0]['valoare'] <= hist['data'][-1]['valoare']


def test_history_1h_aggregation(app, setup, admin):
    with app.app_context():
        s = iot_ingest.create_senzor('H-2', 'X', 'temperatura',
                                       element_bim_id=setup['el_id'], user=admin)
        # 3 citiri in aceeasi ora
        base = datetime(2026, 5, 10, 12, 0)
        iot_ingest.ingest_reading(s, 10, ts=base)
        iot_ingest.ingest_reading(s, 20, ts=base + timedelta(minutes=20))
        iot_ingest.ingest_reading(s, 30, ts=base + timedelta(minutes=45))
        # 1 citire in ora urmatoare
        iot_ingest.ingest_reading(s, 50, ts=base + timedelta(hours=1, minutes=15))

        hist = iot_query.get_history(s.id,
                                       from_ts=base - timedelta(hours=1),
                                       to_ts=base + timedelta(hours=3),
                                       agg='1h')
        # 2 bucket-uri (1 ora + ora urmatoare)
        assert hist['count'] == 2
        # Prima ora: min=10, max=30, avg=20
        first = hist['data'][0]
        assert first['min'] == 10
        assert first['max'] == 30
        assert first['avg'] == 20.0


def test_history_invalid_agg_raises(app, setup, admin):
    with app.app_context():
        s = iot_ingest.create_senzor('H-3', 'X', 'temperatura',
                                       element_bim_id=setup['el_id'], user=admin)
        with pytest.raises(ValueError):
            iot_query.get_history(s.id, agg='invalid')


def test_get_active_alerts(app, setup, admin):
    with app.app_context():
        from models import SensorAlert
        s = iot_ingest.create_senzor('AL-1', 'X', 'temperatura',
                                       element_bim_id=setup['el_id'],
                                       threshold_max=20, user=admin)
        # Trigger 2 alerts (different sensors)
        s2 = iot_ingest.create_senzor('AL-2', 'X', 'co2',
                                        element_bim_id=setup['el_id'],
                                        threshold_max=400, user=admin)
        iot_ingest.ingest_reading(s, 30)
        iot_ingest.ingest_reading(s2, 800)
        active = iot_query.get_active_alerts()
        # Cel putin 2 alerte deschise
        assert len(active) >= 2

        # Filtrare pe senzor
        active_s = iot_query.get_active_alerts(senzor_id=s.id)
        assert len(active_s) == 1
        assert active_s[0].senzor_id == s.id
