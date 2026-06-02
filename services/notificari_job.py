"""
Job APScheduler care scaneaza TermenUrmarit si emite notificari (Faza 14).

Rulare zilnica la 06:00 UTC (configurabil prin env var NOTIFICARI_JOB_HOUR).

Reguli:
  1. Pentru fiecare TermenUrmarit cu status='activ' si data_scadenta < today
     -> marcheaza status='expirat' + emit notificare 'termen_depasit' la
     toti utilizatorii activi din proiect.
  2. Pentru fiecare TermenUrmarit cu status='activ' si
     data_scadenta - zile_anticipare <= today <= data_scadenta
     -> emit notificare 'termen_apropiat'.
  3. Daca exista ReguliNotificareProiect(email_activ=True, tip_eveniment)
     pentru proiect -> trimit si email la destinatari (graceful daca SMTP
     lipseste).

Idempotenta: helper-ul creeaza_notificare verifica daca exista deja o
notificare cu acelasi (utilizator, tip, entitate_referinta, id_entitate)
in aceeasi zi.

Pentru testare manuala fara APScheduler:
  flask job-notificari
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Optional

from models import (
    db, TermenUrmarit, NotificareApp, Utilizator,
    ReguliNotificareProiect,
)
from services.notificari_app import creeaza_notificare
from services.email_notif import trimite_email_termen, smtp_configured
from services.feature_flags import is_enabled


_logger = logging.getLogger(__name__)


def ruleaza_job_notificari(today: Optional[date] = None) -> dict:
    """
    Punctul de intrare al job-ului.

    Returneaza dict cu statistici:
        {
            'termene_scanate': int,
            'termene_expirate': int,    # marcate ca expirate in aceasta rulare
            'notificari_create': int,
            'emailuri_trimise': int,
        }
    """
    if today is None:
        today = date.today()
    stats = {
        'termene_scanate': 0,
        'termene_expirate': 0,
        'notificari_create': 0,
        'emailuri_trimise': 0,
    }

    # Scan TermenUrmarit activ
    termene_active = TermenUrmarit.query.filter_by(status='activ').all()
    stats['termene_scanate'] = len(termene_active)

    for termen in termene_active:
        zile_pana = (termen.data_scadenta - today).days
        anticipare = termen.zile_anticipare or 7

        if zile_pana < 0:
            # 1. Expirat
            termen.status = 'expirat'
            stats['termene_expirate'] += 1
            tip_notif = 'termen_depasit'
            titlu = f'Termen depasit cu {abs(zile_pana)} zile'
        elif zile_pana <= anticipare:
            # 2. Aproape de scadenta
            tip_notif = 'termen_apropiat'
            titlu = (f'Termen scade in {zile_pana} zile'
                     if zile_pana > 0 else 'Termen scade astazi')
        else:
            # Nu e in interval, sarim
            continue

        # Identific destinatarii in-app
        destinatari_useri = _get_destinatari_utilizatori(termen)
        emails_externe = _get_emails_externe(termen, tip_notif)

        mesaj = _construieste_mesaj(termen, zile_pana)
        link_url = f'/contracte/proiect/{termen.proiect_id}'  # link generic proiect

        # In-app notifications
        for user in destinatari_useri:
            n = creeaza_notificare(
                utilizator_id=user.id,
                tip=tip_notif,
                titlu=titlu,
                mesaj=mesaj,
                link_url=link_url,
                entitate_referinta='termen_urmarit',
                id_entitate_referinta=termen.id,
                tenant_id=termen.tenant_id,
            )
            if n is not None:
                stats['notificari_create'] += 1

        # Email (daca config + flag activ)
        if (emails_externe and smtp_configured()
                and is_enabled('controale-contract-notificari-email',
                               tenant_id=termen.tenant_id)):
            ok = trimite_email_termen(
                destinatari=emails_externe,
                termen_titlu=titlu,
                data_scadenta=termen.data_scadenta,
                zile_pana_la_scadenta=zile_pana,
                link_url=link_url,
            )
            if ok:
                stats['emailuri_trimise'] += 1

    db.session.commit()
    stats['evm_risc'] = alerteaza_evm_risc(today)
    _logger.info('Job notificari rulat: %s', stats)
    return stats


def alerteaza_evm_risc(today: Optional[date] = None) -> int:
    """Notifica managerii proiectelor active cu risc EVM (SPI/CPI sub prag).
    Idempotent pe zi (creeaza_notificare nu dubleaza). Intoarce nr. create."""
    from models import db, Proiect
    from services.evm import risc_proiect
    n = 0
    for p in Proiect.query.filter_by(status='activ').all():
        try:
            r = risc_proiect(p.id)
        except Exception:
            r = None
        if not r or r['status'] == 'ok' or not p.manager_id:
            continue
        creeaza_notificare(
            utilizator_id=p.manager_id, tip='evm_risc',
            titlu=f"Proiect {p.cod_proiect}: SPI {r['spi']} / CPI {r['cpi']} ({r['status']})",
            mesaj=f"Avans real {r['ev_pct']}%. Verifica graficul si bugetul in EVM.",
            entitate_referinta='proiect', id_entitate_referinta=p.id)
        n += 1
    db.session.commit()
    return n


def _get_destinatari_utilizatori(termen: TermenUrmarit) -> list[Utilizator]:
    """
    Returneaza utilizatorii care primesc notificari in-app pentru un termen.

    Strategie: toti utilizatorii activi din tenant-ul termenului
    (sau toti utilizatorii activi daca tenant_id=None).
    Filtru aditional: doar useri cu rol manager/admin (operatorii nu
    primesc spam pentru termene de management).
    """
    q = Utilizator.query.filter_by(activ=True)
    if termen.tenant_id is not None:
        q = q.filter(db.or_(Utilizator.tenant_id == termen.tenant_id,
                            Utilizator.tenant_id.is_(None)))
    q = q.filter(Utilizator.rol.in_(['admin', 'manager']))
    return q.all()


def _get_emails_externe(termen: TermenUrmarit, tip_notif: str) -> list[str]:
    """
    Extrage emailurile destinatari din ReguliNotificareProiect pentru proiect.
    """
    regula = ReguliNotificareProiect.query.filter_by(
        proiect_id=termen.proiect_id,
        tip_eveniment=tip_notif,
        email_activ=True,
    ).first()
    if regula is None:
        return []
    return regula.email_destinatari or []


def _construieste_mesaj(termen: TermenUrmarit, zile_pana: int) -> str:
    parts = [
        f'Tip regula: {termen.tip_regula}',
        f'Data scadenta: {termen.data_scadenta}',
        f'Sursa: {termen.entitate_sursa} #{termen.id_entitate_sursa}',
    ]
    if zile_pana < 0:
        parts.append(f'DEPASIT cu {abs(zile_pana)} zile.')
    else:
        parts.append(f'Mai sunt {zile_pana} zile pana la scadenta.')
    if termen.note:
        parts.append(f'Note: {termen.note}')
    return '\n'.join(parts)


def init_scheduler(app):
    """
    Inregistreaza job-ul in APScheduler atasat la app.

    Apelat din app.py la create_app(). NU pornește scheduler daca rulam in
    contextul testing (TESTING=True) sau daca env var DISABLE_SCHEDULER e
    setat (ex: pentru CI).
    """
    if app.config.get('TESTING'):
        return None
    if os.environ.get('DISABLE_SCHEDULER', '').lower() in ('true', '1', 'yes'):
        return None

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        _logger.warning('APScheduler nu e instalat. Job-ul de notificari nu va rula.')
        return None

    hour = int(os.environ.get('NOTIFICARI_JOB_HOUR', '6'))
    scheduler = BackgroundScheduler(daemon=True)

    def _wrapped_job():
        with app.app_context():
            try:
                ruleaza_job_notificari()
            except Exception as e:
                _logger.exception('Job notificari a crapat: %s', e)

    scheduler.add_job(
        _wrapped_job,
        trigger='cron',
        hour=hour,
        minute=0,
        id='notificari_job_zilnic',
        replace_existing=True,
    )

    # Backup automat zilnic al bazei de date (self-hosted, cu rotatie)
    backup_hour = int(os.environ.get('BACKUP_JOB_HOUR', '3'))
    backup_max = int(os.environ.get('BACKUP_MAX', '14'))

    def _wrapped_backup():
        with app.app_context():
            try:
                from services.backup import ruleaza_backup_automat
                r = ruleaza_backup_automat(backup_max)
                _logger.info('Backup automat: %s', r)
            except Exception as e:
                _logger.exception('Backup automat a crapat: %s', e)

    scheduler.add_job(
        _wrapped_backup,
        trigger='cron',
        hour=backup_hour,
        minute=0,
        id='backup_zilnic',
        replace_existing=True,
    )

    scheduler.start()
    _logger.info('APScheduler pornit - notificari %02d:00, backup %02d:00.',
                 hour, backup_hour)
    app.extensions['apscheduler_notificari'] = scheduler
    return scheduler
