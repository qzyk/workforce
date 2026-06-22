"""
Teste unit pentru services.iot_ingest.
"""

from datetime import datetime, timedelta
import pytest

from models import (db, Senzor, SensorReading, SensorAlert,
                    ElementBIM, Cladire, Santier, Utilizator, AuditLog)
from services import iot_ingest


@pytest.fixture
def admin(app):
    with app.app_context():
        u = Utilizator.query.filter_by(email='iot_admin@test.local').first()
        if not u:
            u = Utilizator(nume='IoT', prenume='X', email='iot_admin@test.local',
                           rol='admin', activ=True)
            u.set_password('x'); db.session.add(u); db.session.commit()
        yield u


@pytest.fixture
def element(app):
    with app.app_context():
        s = Santier(cod='S-IOT', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        el = ElementBIM(cladire_id=c.id, cod='E1', tip_element='wall',
                        status='construit', nume='W')
        db.session.add(el); db.session.commit()
        yield el.id


# ====================================================
# create_senzor
# ====================================================

def test_create_senzor_generates_token(app, element, admin):
    with app.app_context():
        s = iot_ingest.create_senzor(
            cod='TEMP-001', nume='Test temp', tip='temperatura',
            element_bim_id=element, threshold_min=18, threshold_max=26,
            user=admin,
        )
        assert s.id is not None
        assert s.api_key is not None
        assert len(s.api_key) == 64  # hex(32 bytes) = 64 chars
        assert s.unitate == '°C'  # auto-from tip


def test_create_senzor_invalid_tip_raises(app, element, admin):
    with app.app_context():
        with pytest.raises(ValueError):
            iot_ingest.create_senzor('X', 'X', 'tip_inexistent',
                                       element_bim_id=element, user=admin)


def test_create_senzor_without_location_raises(app, admin):
    with app.app_context():
        with pytest.raises(ValueError):
            iot_ingest.create_senzor('X', 'X', 'temperatura', user=admin)


def test_rotate_api_key_changes_key(app, element, admin):
    with app.app_context():
        s = iot_ingest.create_senzor(
            cod='ROT-1', nume='X', tip='temperatura',
            element_bim_id=element, user=admin,
        )
        old_key = s.api_key
        new_key = iot_ingest.rotate_api_key(s)
        assert new_key != old_key
        assert len(new_key) == 64


# ====================================================
# authenticate_token
# ====================================================

def test_authenticate_token_returns_senzor(app, element, admin):
    with app.app_context():
        s = iot_ingest.create_senzor('AUTH-1', 'X', 'temperatura',
                                       element_bim_id=element, user=admin)
        token = s.api_key
        result = iot_ingest.authenticate_token(token)
        assert result is not None
        assert result.id == s.id


def test_authenticate_invalid_token_returns_none(app):
    with app.app_context():
        assert iot_ingest.authenticate_token('xxx') is None
        assert iot_ingest.authenticate_token('') is None


def test_authenticate_inactive_senzor_returns_none(app, element, admin):
    with app.app_context():
        s = iot_ingest.create_senzor('INACTIV', 'X', 'temperatura',
                                       element_bim_id=element, user=admin)
        token = s.api_key
        s.activ = False
        db.session.commit()
        assert iot_ingest.authenticate_token(token) is None


# ====================================================
# ingest_reading + alert logic
# ====================================================

def test_ingest_reading_normal_value(app, element, admin):
    with app.app_context():
        s = iot_ingest.create_senzor('ING-1', 'X', 'temperatura',
                                       element_bim_id=element,
                                       threshold_min=18, threshold_max=26,
                                       user=admin)
        result = iot_ingest.ingest_reading(s, 22.5)
        assert result['alert_created'] is False
        assert result['threshold_violated'] is None
        assert SensorReading.query.filter_by(senzor_id=s.id).count() == 1
        # Cache senzor updated
        s_after = Senzor.query.get(s.id)
        assert float(s_after.ultima_valoare) == 22.5
        assert s_after.ultima_citire_at is not None


def test_ingest_below_min_creates_alert(app, element, admin):
    with app.app_context():
        s = iot_ingest.create_senzor('ING-MIN', 'X', 'temperatura',
                                       element_bim_id=element,
                                       threshold_min=18, threshold_max=26,
                                       user=admin)
        result = iot_ingest.ingest_reading(s, 10.0)
        assert result['alert_created'] is True
        assert result['threshold_violated'] == 'sub_min'
        alert = SensorAlert.query.get(result['alert_id'])
        assert alert.tip == 'sub_min'
        assert alert.severitate in ('medie', 'mare', 'critica')


def test_ingest_above_max_creates_alert(app, element, admin):
    with app.app_context():
        s = iot_ingest.create_senzor('ING-MAX', 'X', 'temperatura',
                                       element_bim_id=element,
                                       threshold_min=18, threshold_max=26,
                                       user=admin)
        result = iot_ingest.ingest_reading(s, 50.0)
        assert result['alert_created'] is True
        assert result['threshold_violated'] == 'peste_max'


def test_consecutive_alerts_reuse_open_alert(app, element, admin):
    """Doua citiri peste max consecutive -> un singur alert deschis."""
    with app.app_context():
        s = iot_ingest.create_senzor('ING-DUP', 'X', 'temperatura',
                                       element_bim_id=element,
                                       threshold_max=26, user=admin)
        r1 = iot_ingest.ingest_reading(s, 30.0)
        r2 = iot_ingest.ingest_reading(s, 35.0)
        # Acelasi alert_id (refolosit), nu unul nou
        assert r1['alert_id'] == r2['alert_id']
        # Prima citire creeaza alerta noua; a doua o refoloseste/escaladeaza.
        assert r1['alert_new'] is True
        assert r2['alert_new'] is False
        # Ambele 'ating' o alerta, deci alert_created ramane True pe ambele.
        assert r1['alert_created'] is True
        assert r2['alert_created'] is True
        # Total: 1 alert in DB
        assert SensorAlert.query.filter_by(senzor_id=s.id, status='noua').count() == 1


def test_ingest_eroare_calitate_skips_threshold(app, element, admin):
    """Citirile cu calitate='eroare' nu genereaza alerte."""
    with app.app_context():
        s = iot_ingest.create_senzor('ING-ERR', 'X', 'temperatura',
                                       element_bim_id=element,
                                       threshold_max=26, user=admin)
        result = iot_ingest.ingest_reading(s, 999.0, calitate='eroare')
        assert result['alert_created'] is False


def test_severity_increases_with_distance(app, element, admin):
    with app.app_context():
        s = iot_ingest.create_senzor('ING-SEV', 'X', 'temperatura',
                                       element_bim_id=element,
                                       threshold_max=20, user=admin)
        # Putin peste -> medie
        r = iot_ingest.ingest_reading(s, 21.0)
        a = SensorAlert.query.get(r['alert_id'])
        assert a.severitate == 'medie'


# ====================================================
# Alert transitions
# ====================================================

def test_transition_alert_noua_to_confirmata(app, element, admin):
    with app.app_context():
        s = iot_ingest.create_senzor('T-1', 'X', 'temperatura',
                                       element_bim_id=element,
                                       threshold_max=20, user=admin)
        r = iot_ingest.ingest_reading(s, 30.0)
        a = SensorAlert.query.get(r['alert_id'])
        iot_ingest.transition_alert(a, 'confirmata', admin)
        assert a.status == 'confirmata'
        assert a.data_confirmare is not None


def test_transition_invalid_raises(app, element, admin):
    with app.app_context():
        s = iot_ingest.create_senzor('T-2', 'X', 'temperatura',
                                       element_bim_id=element,
                                       threshold_max=20, user=admin)
        r = iot_ingest.ingest_reading(s, 30.0)
        a = SensorAlert.query.get(r['alert_id'])
        iot_ingest.transition_alert(a, 'rezolvata', admin)
        # Din rezolvata nu mai se poate
        with pytest.raises(ValueError):
            iot_ingest.transition_alert(a, 'confirmata', admin)


# ====================================================
# ingest_batch (IoT Faza 3) - un commit pe lot
# ====================================================

def test_ingest_batch_insereaza_n_citiri(app, element, admin):
    """ingest_batch cu N citiri -> N randuri inserate, cache pe ultima."""
    with app.app_context():
        s = iot_ingest.create_senzor('BATCH-1', 'X', 'temperatura',
                                       element_bim_id=element, user=admin)
        sid = s.id
        base = datetime(2026, 6, 22, 8, 0, 0)
        readings = [{'valoare': 20 + i, 'ts': (base + timedelta(minutes=i)).isoformat()}
                    for i in range(5)]
        res = iot_ingest.ingest_batch(s, readings)
        assert res['ingested'] == 5
        assert res['alerts_created'] == 0
        assert res['errors'] == []
        assert SensorReading.query.filter_by(senzor_id=sid).count() == 5
        # Cache reflecta ultima citire procesata.
        s2 = Senzor.query.get(sid)
        assert float(s2.ultima_valoare) == 24.0


def test_ingest_batch_un_singur_commit(app, element, admin, monkeypatch):
    """Tot lotul se scrie cu UN singur db.session.commit()."""
    from models import db as _db
    with app.app_context():
        s = iot_ingest.create_senzor('BATCH-COMMIT', 'X', 'temperatura',
                                       element_bim_id=element, user=admin)
        readings = [{'valoare': float(v)} for v in range(10)]

        calls = {'n': 0}
        orig_commit = _db.session.commit

        def _counting_commit():
            calls['n'] += 1
            return orig_commit()

        monkeypatch.setattr(_db.session, 'commit', _counting_commit)
        iot_ingest.ingest_batch(s, readings)
        assert calls['n'] == 1  # un singur commit pentru tot lotul


def test_ingest_batch_genereaza_alerta(app, element, admin):
    """O citire peste threshold in lot genereaza alerta (numarata in sumar)."""
    with app.app_context():
        s = iot_ingest.create_senzor('BATCH-ALERT', 'X', 'temperatura',
                                       element_bim_id=element,
                                       threshold_max=25, user=admin)
        sid = s.id
        readings = [{'valoare': 20.0}, {'valoare': 40.0}, {'valoare': 21.0}]
        res = iot_ingest.ingest_batch(s, readings)
        assert res['ingested'] == 3
        assert res['alerts_created'] == 1
        assert SensorAlert.query.filter_by(senzor_id=sid, tip='peste_max').count() == 1


def test_ingest_batch_multi_alerta_acelasi_lot_nu_umfla_sumarul(app, element, admin):
    """Mai multe citiri peste prag in ACELASI lot -> O singura alerta noua.

    Reproduce gaura din review: [30, 40, 35] cu threshold_max=25 ating toate
    pragul, dar refolosesc / escaladeaza aceeasi alerta deschisa. 'alerts_created'
    trebuie sa numere DOAR alerta noua (1), nu fiecare citire peste prag (3).
    """
    with app.app_context():
        s = iot_ingest.create_senzor('BATCH-MULTI', 'X', 'temperatura',
                                       element_bim_id=element,
                                       threshold_max=25, user=admin)
        sid = s.id
        readings = [{'valoare': 30.0}, {'valoare': 40.0}, {'valoare': 35.0}]
        res = iot_ingest.ingest_batch(s, readings)
        assert res['ingested'] == 3
        # O singura alerta in DB (de-dup pe tip + status noua)...
        assert SensorAlert.query.filter_by(senzor_id=sid, tip='peste_max').count() == 1
        # ...si sumarul reflecta exact o alerta noua, nu trei.
        assert res['alerts_created'] == 1
        # Doar prima citire e alerta noua; celelalte refolosesc/escaladeaza.
        assert [r['alert_new'] for r in res['results']] == [True, False, False]
        # Escaladare la critica (40 e mult peste 25), alert_id stabil pe tot lotul.
        ids = {r['alert_id'] for r in res['results']}
        assert len(ids) == 1


def test_ingest_batch_elemente_invalide_raportate(app, element, admin):
    """Elementele invalide nu rup lotul; sunt raportate in 'errors'."""
    with app.app_context():
        s = iot_ingest.create_senzor('BATCH-ERR', 'X', 'temperatura',
                                       element_bim_id=element, user=admin)
        sid = s.id
        readings = [
            {'valoare': 20.0},          # ok
            {'nimic': 1},               # lipsa valoare
            {'valoare': 'abc'},         # ne-numeric
            {'valoare': 22.0, 'ts': 'nu-e-data'},  # ts invalid
            {'valoare': 23.0},          # ok
        ]
        res = iot_ingest.ingest_batch(s, readings)
        assert res['ingested'] == 2
        assert len(res['errors']) == 3
        assert SensorReading.query.filter_by(senzor_id=sid).count() == 2


def test_ingest_single_neschimbat_regresie(app, element, admin):
    """Regresie: ingest_reading single ramane identic (commit default, result shape)."""
    with app.app_context():
        s = iot_ingest.create_senzor('SINGLE-REG', 'X', 'temperatura',
                                       element_bim_id=element,
                                       threshold_max=25, user=admin)
        sid = s.id
        r = iot_ingest.ingest_reading(s, 30.0)
        assert set(r.keys()) == {'reading_id', 'ts', 'alert_created', 'alert_new',
                                 'alert_id', 'threshold_violated'}
        assert r['alert_created'] is True
        assert r['alert_new'] is True
        assert r['threshold_violated'] == 'peste_max'
        assert SensorReading.query.filter_by(senzor_id=sid).count() == 1
