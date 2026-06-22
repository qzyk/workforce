"""
Teste pentru IoT Faza 3: detectie senzor offline.

Acopera:
- senzor cu citire veche peste pragul offline -> alerta tip='offline';
- idempotenta: a 2-a rulare NU creeaza alta alerta (de-dup pe alerta deschisa);
- senzor cu citire recenta -> nicio alerta;
- senzor cu offline_timeout_sec NULL -> ignorat (detectie dezactivata);
- senzor fara nicio citire (ultima_citire_at NULL) -> nu e marcat offline;
- dupa rezolvarea alertei, o noua cadere genereaza din nou alerta;
- reutilizarea dispatch_alert din Faza 1 (notificare cu flag ON).
"""

from datetime import datetime, timedelta
import pytest

from models import (db, Senzor, SensorAlert, ElementBIM, Cladire, Santier,
                    Utilizator, NotificareApp, RealtimeEvent)
from services import iot_ingest
from services import iot_offline
from services import feature_flags as ff


# ====================================================
# Fixtures
# ====================================================

@pytest.fixture
def admin(app):
    with app.app_context():
        u = Utilizator.query.filter_by(email='iot_off_admin@test.local').first()
        if not u:
            u = Utilizator(nume='Off', prenume='Admin', email='iot_off_admin@test.local',
                           rol='admin', activ=True)
            u.set_password('x'); db.session.add(u); db.session.commit()
        yield u


@pytest.fixture
def element(app):
    with app.app_context():
        s = Santier(cod='S-OFF', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        el = ElementBIM(cladire_id=c.id, cod='E1', tip_element='wall',
                        status='construit', nume='W')
        db.session.add(el); db.session.commit()
        yield el.id


@pytest.fixture(autouse=True)
def _curat_notificari(app):
    """Curat NotificareApp intre teste (conftest nu il sterge)."""
    yield
    with app.app_context():
        try:
            NotificareApp.query.delete()
            db.session.commit()
        except Exception:
            db.session.rollback()


def _make_senzor(element, admin, cod, *, timeout_sec=None, ultima_citire_at='AUTO'):
    """Creeaza un senzor cu offline_timeout_sec + ultima_citire_at injectate."""
    s = iot_ingest.create_senzor(
        cod=cod, nume='X', tip='temperatura',
        element_bim_id=element, user=admin)
    if timeout_sec is not None:
        s.offline_timeout_sec = timeout_sec
    if ultima_citire_at != 'AUTO':
        s.ultima_citire_at = ultima_citire_at
    db.session.commit()
    return s


# ====================================================
# Detectie de baza
# ====================================================

def test_senzor_cu_citire_veche_genereaza_alerta_offline(app, element, admin):
    with app.app_context():
        now = datetime(2026, 6, 22, 12, 0, 0)
        # ultima citire acum 2h, prag 60s -> offline.
        s = _make_senzor(element, admin, 'OFF-OLD', timeout_sec=60,
                         ultima_citire_at=now - timedelta(hours=2))
        sid = s.id

        stats = iot_offline.check_offline(now=now)
        assert stats['offline'] == 1
        assert stats['alerte_noi'] == 1

        alerta = SensorAlert.query.filter_by(senzor_id=sid, tip='offline').first()
        assert alerta is not None
        assert alerta.status == 'noua'
        assert alerta.severitate == 'mare'


def test_idempotent_nu_creeaza_a_doua_alerta(app, element, admin):
    """A 2-a rulare NU creeaza alta alerta offline (de-dup pe alerta deschisa)."""
    with app.app_context():
        now = datetime(2026, 6, 22, 12, 0, 0)
        s = _make_senzor(element, admin, 'OFF-IDEM', timeout_sec=60,
                         ultima_citire_at=now - timedelta(hours=2))
        sid = s.id

        s1 = iot_offline.check_offline(now=now)
        assert s1['alerte_noi'] == 1

        # A doua rulare, ceva mai tarziu - senzorul tot offline.
        s2 = iot_offline.check_offline(now=now + timedelta(minutes=5))
        assert s2['offline'] == 1
        assert s2['alerte_noi'] == 0       # nicio alerta noua
        assert s2['deja_alertat'] == 1     # de-dup

        # O singura alerta offline in DB.
        assert SensorAlert.query.filter_by(senzor_id=sid, tip='offline').count() == 1


def test_senzor_cu_citire_recenta_nu_genereaza_alerta(app, element, admin):
    with app.app_context():
        now = datetime(2026, 6, 22, 12, 0, 0)
        # ultima citire acum 30s, prag 300s -> online.
        s = _make_senzor(element, admin, 'OFF-FRESH', timeout_sec=300,
                         ultima_citire_at=now - timedelta(seconds=30))
        sid = s.id

        stats = iot_offline.check_offline(now=now)
        assert stats['offline'] == 0
        assert stats['alerte_noi'] == 0
        assert SensorAlert.query.filter_by(senzor_id=sid, tip='offline').count() == 0


def test_timeout_null_este_ignorat(app, element, admin):
    """offline_timeout_sec NULL = detectie dezactivata (skip)."""
    with app.app_context():
        now = datetime(2026, 6, 22, 12, 0, 0)
        s = _make_senzor(element, admin, 'OFF-NULL', timeout_sec=None,
                         ultima_citire_at=now - timedelta(days=5))
        sid = s.id

        stats = iot_offline.check_offline(now=now)
        assert stats['verificati'] == 0   # nici macar nu intra in scan
        assert stats['offline'] == 0
        assert SensorAlert.query.filter_by(senzor_id=sid, tip='offline').count() == 0


def test_senzor_fara_citiri_nu_e_offline(app, element, admin):
    """ultima_citire_at NULL -> fara referinta de staleness, nu marcam offline."""
    with app.app_context():
        now = datetime(2026, 6, 22, 12, 0, 0)
        s = _make_senzor(element, admin, 'OFF-NEVER', timeout_sec=60,
                         ultima_citire_at=None)
        sid = s.id

        stats = iot_offline.check_offline(now=now)
        assert stats['verificati'] == 1   # eligibil (timeout setat)
        assert stats['offline'] == 0      # dar fara citire -> nu offline
        assert SensorAlert.query.filter_by(senzor_id=sid, tip='offline').count() == 0


def test_timeout_invalid_zero_ignorat(app, element, admin):
    """offline_timeout_sec <= 0 e tratat ca dezactivat."""
    with app.app_context():
        now = datetime(2026, 6, 22, 12, 0, 0)
        s = _make_senzor(element, admin, 'OFF-ZERO', timeout_sec=0,
                         ultima_citire_at=now - timedelta(days=1))
        stats = iot_offline.check_offline(now=now)
        assert stats['offline'] == 0


def test_dupa_rezolvare_noua_cadere_genereaza_alerta(app, element, admin):
    """Dupa ce alerta offline e rezolvata, o noua cadere genereaza din nou."""
    with app.app_context():
        now = datetime(2026, 6, 22, 12, 0, 0)
        s = _make_senzor(element, admin, 'OFF-REOPEN', timeout_sec=60,
                         ultima_citire_at=now - timedelta(hours=2))
        sid = s.id

        iot_offline.check_offline(now=now)
        alerta = SensorAlert.query.filter_by(senzor_id=sid, tip='offline').first()
        assert alerta is not None

        # Rezolvam manual alerta.
        alerta.status = 'rezolvata'
        db.session.commit()

        # Senzorul tot offline -> o noua alerta (de-dup nu prinde alerte terminale).
        stats = iot_offline.check_offline(now=now + timedelta(minutes=10))
        assert stats['alerte_noi'] == 1
        assert SensorAlert.query.filter_by(senzor_id=sid, tip='offline').count() == 2


# ====================================================
# Reutilizare dispatch_alert (Faza 1)
# ====================================================

def test_offline_dispatch_notificare_cu_flag_on(app, element, admin):
    """Cu flag 'iot-alert-notify' ON, alerta offline produce notificare + SSE."""
    with app.app_context():
        ff.set_flag('iot-alert-notify', True)
        try:
            now = datetime(2026, 6, 22, 12, 0, 0)
            s = _make_senzor(element, admin, 'OFF-NOTIF', timeout_sec=60,
                             ultima_citire_at=now - timedelta(hours=2))
            sid = s.id

            iot_offline.check_offline(now=now)
            alerta = SensorAlert.query.filter_by(senzor_id=sid, tip='offline').first()
            assert alerta is not None
            # dispatch a marcat idempotenta.
            assert alerta.notificat_la is not None
            # Eveniment SSE publicat.
            assert RealtimeEvent.query.filter_by(event_type='sensor_alert').count() >= 1
            # Notificare in-app pentru admin.
            assert NotificareApp.query.filter_by(
                tip='sensor_alert', id_entitate_referinta=alerta.id).count() >= 1
        finally:
            ff.set_flag('iot-alert-notify', False)


def test_offline_flag_off_alerta_tacuta(app, element, admin):
    """Cu flag OFF, alerta offline se naste tacut (zero notificari/evenimente)."""
    with app.app_context():
        ff.set_flag('iot-alert-notify', False)
        now = datetime(2026, 6, 22, 12, 0, 0)
        s = _make_senzor(element, admin, 'OFF-SILENT', timeout_sec=60,
                         ultima_citire_at=now - timedelta(hours=2))
        sid = s.id

        iot_offline.check_offline(now=now)
        alerta = SensorAlert.query.filter_by(senzor_id=sid, tip='offline').first()
        assert alerta is not None
        assert alerta.notificat_la is None
        assert RealtimeEvent.query.filter_by(event_type='sensor_alert').count() == 0


# ====================================================
# CLI flask iot-offline
# ====================================================

def test_cli_iot_offline_ruleaza(app, element, admin):
    with app.app_context():
        now_ish = datetime.utcnow() - timedelta(hours=2)
        s = _make_senzor(element, admin, 'OFF-CLI', timeout_sec=60,
                         ultima_citire_at=now_ish)
        sid = s.id

    runner = app.test_cli_runner()
    result = runner.invoke(args=['iot-offline'])
    assert result.exit_code == 0
    assert 'Detectie offline IoT' in result.output

    with app.app_context():
        assert SensorAlert.query.filter_by(senzor_id=sid, tip='offline').count() == 1
