"""
Serviciu de dispatch pentru alertele IoT (IoT Faza 1).

Inchide bucla alerta senzor -> notificare. Pana acum alertele se nasteau
tacut in DB (services/iot_ingest.ingest_reading) fara niciun canal de iesire.
`dispatch_alert` cupleaza alerta la infrastructura existenta:

  (a) publica un RealtimeEvent('sensor_alert') pe event bus (consum SSE);
  (b) creeaza NotificareApp in-app catre managerii/adminii activi;
  (c) trimite email best-effort DOAR daca SMTP e configurat (try/except).

Idempotenta: marcheaza SensorAlert.notificat_la dupa primul dispatch; nu
re-notifica daca e deja setat (decat la escaladare explicita).

Totul e gated de flag-ul 'iot-alert-notify' (default OFF). Cu flag OFF,
dispatch_alert nu face nimic (ingestul ramane tacut, comportament istoric).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from models import db, SensorAlert, Senzor, Utilizator
from services import feature_flags as ff_svc
from services import notificari_app as notif_svc
from services import realtime as rt_svc
from services import email_notif


_logger = logging.getLogger(__name__)


# Tip NotificareApp pentru alertele IoT (folosit la idempotenta pe zi).
TIP_NOTIFICARE = 'sensor_alert'


def _destinatari_manageri(tenant_id: Optional[int]) -> list[Utilizator]:
    """
    Utilizatorii care primesc notificarea in-app: manageri/admini activi.

    Scope pe tenant ca la notificari_job: tenant-ul alertei + globalii
    (tenant_id IS NULL). Daca alerta nu are tenant, toti managerii activi.
    """
    q = Utilizator.query.filter_by(activ=True)
    if tenant_id is not None:
        q = q.filter(db.or_(Utilizator.tenant_id == tenant_id,
                            Utilizator.tenant_id.is_(None)))
    q = q.filter(Utilizator.rol.in_(['admin', 'manager']))
    return q.all()


def _payload_alerta(alert: SensorAlert, senzor: Optional[Senzor]) -> dict:
    """Payload pentru evenimentul SSE + (refolosit la) email."""
    return {
        'alert_id': alert.id,
        'senzor_id': alert.senzor_id,
        'senzor_cod': senzor.cod if senzor else None,
        'tip': alert.tip,
        'severitate': alert.severitate,
        'valoare': float(alert.valoare) if alert.valoare is not None else None,
        'threshold_violat': (float(alert.threshold_violat)
                             if alert.threshold_violat is not None else None),
        'mesaj': alert.mesaj,
        'status': alert.status,
    }


def dispatch_alert(alert: SensorAlert, *,
                   escalada: bool = False,
                   commit: bool = False) -> dict:
    """
    Trimite o alerta de senzor pe canalele de notificare.

    Parametri:
        alert     - SensorAlert tocmai creat sau escaladat.
        escalada  - True daca alerta exista deja dar severitatea a crescut;
                    in acest caz re-notificam chiar daca notificat_la e setat.
        commit    - daca True, face db.session.commit() la final. Implicit
                    False ca sa se uneasca cu commit-ul ingestului (un singur
                    write pe SQLite - evita 'database is locked').

    Returneaza un sumar cu ce canale au fost activate.

    Gated de flag 'iot-alert-notify' (default OFF). Cu OFF -> no-op.
    Idempotent: daca alert.notificat_la e setat si nu e escaladare, nu reface.
    """
    rezultat = {
        'dispatched': False,
        'event_published': False,
        'notificari_create': 0,
        'email_trimis': False,
        'skipped': None,
    }

    if alert is None:
        rezultat['skipped'] = 'alert_none'
        return rezultat

    # Gate pe flag - cu OFF ramane tacut (comportament istoric).
    if not ff_svc.is_enabled('iot-alert-notify', tenant_id=alert.tenant_id):
        rezultat['skipped'] = 'flag_off'
        return rezultat

    # Idempotenta: daca a fost deja notificata si nu e escaladare -> nimic.
    if alert.notificat_la is not None and not escalada:
        rezultat['skipped'] = 'deja_notificat'
        return rezultat

    senzor = Senzor.query.get(alert.senzor_id) if alert.senzor_id else None
    payload = _payload_alerta(alert, senzor)
    link_url = f'/bim/alerts?status={alert.status}'

    # (a) Eveniment SSE - commit=False ca sa intre in tranzactia ingestului.
    try:
        rt_svc.publish_event(
            'sensor_alert',
            payload=payload,
            tenant_id=alert.tenant_id,
            commit=False,
        )
        rezultat['event_published'] = True
    except Exception as e:  # best-effort, nu rupe ingestul
        _logger.warning('dispatch_alert publish_event a esuat: %s', e)

    # (b) Notificari in-app catre manageri/admini.
    titlu = f'Alerta senzor ({alert.severitate}): {payload.get("senzor_cod") or alert.senzor_id}'
    try:
        for u in _destinatari_manageri(alert.tenant_id):
            n = notif_svc.creeaza_notificare(
                utilizator_id=u.id,
                tip=TIP_NOTIFICARE,
                titlu=titlu[:255],
                mesaj=alert.mesaj,
                link_url=link_url,
                entitate_referinta='sensor_alert',
                id_entitate_referinta=alert.id,
                tenant_id=alert.tenant_id,
                # La escaladare permitem o noua notificare in aceeasi zi.
                skip_duplicate_today=not escalada,
            )
            if n is not None:
                rezultat['notificari_create'] += 1
    except Exception as e:  # best-effort
        _logger.warning('dispatch_alert creeaza_notificare a esuat: %s', e)

    # (c) Email best-effort - DOAR daca SMTP e configurat.
    try:
        if email_notif.smtp_configured():
            emails = [u.email for u in _destinatari_manageri(alert.tenant_id)
                      if getattr(u, 'email', None)]
            if emails:
                corp = (
                    f'{alert.mesaj}\n\n'
                    f'Severitate: {alert.severitate}\n'
                    f'Tip: {alert.tip}\n'
                    f'Senzor: {payload.get("senzor_cod") or alert.senzor_id}\n'
                )
                rezultat['email_trimis'] = email_notif.trimite_email(
                    emails, titlu, corp)
    except Exception as e:  # best-effort, nu rupe ingestul
        _logger.warning('dispatch_alert trimite_email a esuat: %s', e)

    # Marcam idempotenta dupa dispatch.
    alert.notificat_la = datetime.utcnow()
    rezultat['dispatched'] = True

    if commit:
        db.session.commit()

    return rezultat
