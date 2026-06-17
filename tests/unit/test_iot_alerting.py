"""
Teste pentru IoT Faza 1: inchiderea buclei alerta senzor -> notificare.

Acopera:
- alerta noua -> dispatch creeaza notificare in-app + publica eveniment SSE
  (flag 'iot-alert-notify' ON);
- SMTP neconfigurat -> fallback fara crash (email_trimis False, restul OK);
- idempotenta: a 2-a oara dispatch_alert nu re-notifica (notificat_la setat);
- escaladare: severitatea creste -> re-notificare permisa;
- regresie flag OFF: ingestul nu produce nicio notificare / niciun eveniment
  (comportament istoric, zero notificari).
"""

import pytest

from models import (db, Senzor, SensorAlert, ElementBIM, Cladire, Santier,
                    Utilizator, NotificareApp, RealtimeEvent)
from services import iot_ingest
from services import iot_alerting
from services import realtime as rt
from services import feature_flags as ff


# ====================================================
# Fixtures
# ====================================================

@pytest.fixture
def manager(app):
    with app.app_context():
        u = Utilizator.query.filter_by(email='iot_mgr@test.local').first()
        if not u:
            u = Utilizator(nume='Mgr', prenume='IoT', email='iot_mgr@test.local',
                           rol='manager', activ=True)
            u.set_password('x'); db.session.add(u); db.session.commit()
        return u.id


@pytest.fixture
def element(app):
    with app.app_context():
        s = Santier(cod='S-ALERT', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        el = ElementBIM(cladire_id=c.id, cod='E1', tip_element='wall',
                        status='construit', nume='W')
        db.session.add(el); db.session.commit()
        yield el.id


@pytest.fixture
def flag_on(app):
    """Activeaza flag-ul iot-alert-notify global; reset la final."""
    with app.app_context():
        ff.set_flag('iot-alert-notify', True)
    yield
    with app.app_context():
        ff.set_flag('iot-alert-notify', False)


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


def _make_senzor(element, manager_id, cod):
    u = Utilizator.query.get(manager_id)
    return iot_ingest.create_senzor(
        cod=cod, nume='X', tip='temperatura',
        element_bim_id=element, threshold_max=26, user=u)


# ====================================================
# Flag ON: dispatch creeaza notificare + eveniment SSE
# ====================================================

def test_alerta_noua_creeaza_notificare_si_eveniment(app, element, manager, flag_on):
    with app.app_context():
        s = _make_senzor(element, manager, 'AL-NEW')
        result = iot_ingest.ingest_reading(s, 40.0)
        assert result['alert_created'] is True

        # Notificare in-app pentru manager.
        notif = NotificareApp.query.filter_by(
            utilizator_id=manager, tip='sensor_alert',
            id_entitate_referinta=result['alert_id']).first()
        assert notif is not None
        assert notif.link_url and '/bim/alerts' in notif.link_url

        # Eveniment SSE publicat.
        ev = RealtimeEvent.query.filter_by(event_type='sensor_alert').first()
        assert ev is not None

        # notificat_la marcat (idempotenta).
        alert = SensorAlert.query.get(result['alert_id'])
        assert alert.notificat_la is not None


def test_alerta_ajunge_la_abonat_scoped_pe_santier(app, element, manager, flag_on):
    """
    Regresie scope SSE: evenimentul 'sensor_alert' trebuie sa poarte
    santier_id rezolvat din lantul senzorului (element -> cladire -> santier),
    altfel abonatii scoped (?santier_id=X via /api/events/stream) nu il primesc.
    Exercitiem chiar calea de consum: realtime.get_events_since(santier_id=X).
    """
    with app.app_context():
        # Aflam santier-ul din lantul element -> cladire.
        el = ElementBIM.query.get(element)
        cladire = Cladire.query.get(el.cladire_id)
        santier_id = cladire.santier_id
        assert santier_id is not None

        cursor = rt.get_latest_event_id()

        s = _make_senzor(element, manager, 'AL-SCOPE')
        result = iot_ingest.ingest_reading(s, 40.0)
        assert result['alert_created'] is True

        # Evenimentul publicat poarta santier_id-ul corect.
        ev = RealtimeEvent.query.filter_by(event_type='sensor_alert').order_by(
            RealtimeEvent.id.desc()).first()
        assert ev is not None
        assert ev.santier_id == santier_id

        # Abonatul scoped pe santier primeste alerta.
        livrate = rt.get_events_since(cursor, santier_id=santier_id)
        assert any(e.event_type == 'sensor_alert' for e in livrate)

        # Abonatul scoped pe ALT santier NU o primeste (filtru corect).
        livrate_alt = rt.get_events_since(cursor, santier_id=santier_id + 9999)
        assert not any(e.event_type == 'sensor_alert' for e in livrate_alt)


def test_smtp_neconfigurat_fallback_fara_crash(app, element, manager, flag_on, monkeypatch):
    """SMTP nesetat -> email_trimis False, dar in-app + SSE merg, fara exceptie."""
    monkeypatch.delenv('SMTP_HOST', raising=False)
    monkeypatch.delenv('SMTP_FROM', raising=False)
    with app.app_context():
        s = _make_senzor(element, manager, 'AL-SMTP')
        alert = SensorAlert(
            tenant_id=None, senzor_id=s.id, tip='peste_max', severitate='mare',
            valoare=40, threshold_violat=26, mesaj='test', status='noua')
        db.session.add(alert); db.session.flush()
        res = iot_alerting.dispatch_alert(alert, commit=True)
        assert res['dispatched'] is True
        assert res['email_trimis'] is False
        assert res['notificari_create'] >= 1
        assert res['event_published'] is True


def test_idempotent_nu_renotifica(app, element, manager, flag_on):
    """A doua oara dispatch_alert pe aceeasi alerta (notificat_la setat) -> skip."""
    with app.app_context():
        s = _make_senzor(element, manager, 'AL-IDEM')
        alert = SensorAlert(
            tenant_id=None, senzor_id=s.id, tip='peste_max', severitate='mare',
            valoare=40, threshold_violat=26, mesaj='test', status='noua')
        db.session.add(alert); db.session.flush()

        r1 = iot_alerting.dispatch_alert(alert, commit=True)
        assert r1['dispatched'] is True
        nr_dupa_1 = NotificareApp.query.filter_by(
            id_entitate_referinta=alert.id).count()

        r2 = iot_alerting.dispatch_alert(alert, commit=True)
        assert r2['dispatched'] is False
        assert r2['skipped'] == 'deja_notificat'
        nr_dupa_2 = NotificareApp.query.filter_by(
            id_entitate_referinta=alert.id).count()
        assert nr_dupa_2 == nr_dupa_1  # nicio notificare noua


def test_escaladare_renotifica(app, element, manager, flag_on):
    """La escaladare (severitate crescuta) dispatch_alert re-notifica."""
    with app.app_context():
        s = _make_senzor(element, manager, 'AL-ESC')
        alert = SensorAlert(
            tenant_id=None, senzor_id=s.id, tip='peste_max', severitate='medie',
            valoare=28, threshold_violat=26, mesaj='test', status='noua')
        db.session.add(alert); db.session.flush()

        iot_alerting.dispatch_alert(alert, commit=True)
        # Escaladare explicita.
        alert.severitate = 'critica'
        res = iot_alerting.dispatch_alert(alert, escalada=True, commit=True)
        assert res['dispatched'] is True
        assert res['skipped'] is None
        assert res['notificari_create'] >= 1


# ====================================================
# Regresie: flag OFF -> ingest tacut (comportament istoric)
# ====================================================

def test_flag_off_ingest_nu_notifica(app, element, manager):
    """Cu flag OFF: alerta se creeaza in DB dar zero notificari / evenimente."""
    with app.app_context():
        ff.set_flag('iot-alert-notify', False)
        s = _make_senzor(element, manager, 'AL-OFF')
        result = iot_ingest.ingest_reading(s, 40.0)
        assert result['alert_created'] is True

        # Zero notificari in-app.
        assert NotificareApp.query.filter_by(
            id_entitate_referinta=result['alert_id']).count() == 0
        # Zero evenimente SSE de tip sensor_alert.
        assert RealtimeEvent.query.filter_by(event_type='sensor_alert').count() == 0
        # notificat_la ramane NULL.
        alert = SensorAlert.query.get(result['alert_id'])
        assert alert.notificat_la is None


def test_dispatch_direct_flag_off_noop(app, element, manager):
    """dispatch_alert apelat direct cu flag OFF -> no-op (skip flag_off)."""
    with app.app_context():
        ff.set_flag('iot-alert-notify', False)
        s = _make_senzor(element, manager, 'AL-OFF2')
        alert = SensorAlert(
            tenant_id=None, senzor_id=s.id, tip='peste_max', severitate='mare',
            valoare=40, threshold_violat=26, mesaj='test', status='noua')
        db.session.add(alert); db.session.flush()
        res = iot_alerting.dispatch_alert(alert, commit=True)
        assert res['dispatched'] is False
        assert res['skipped'] == 'flag_off'
        assert alert.notificat_la is None
