"""
Detectie senzor offline (IoT Faza 3).

Problema (audit AUDIT_IOT.md): SensorAlert.tip documenteaza 'offline' dar niciun
job nu il genereaza - un senzor mort (gateway cazut, baterie goala) nu produce
nicio alerta, ramane "ultima valoare buna" la nesfarsit.

Solutie: check_offline() scaneaza senzorii activi cu offline_timeout_sec setat
si genereaza o SensorAlert(tip='offline') daca ultima citire e mai veche decat
intervalul configurat. Reutilizeaza dispatch_alert din Faza 1 (services
iot_alerting) pentru notificare in-app + SSE + email best-effort.

Rulat de CLI 'flask iot-offline' (Scheduled Task pe PA).

Idempotenta (nu spam):
  - de-dup pe alerta offline DESCHISA per senzor (status 'noua' sau
    'confirmata'); daca exista deja una, nu cream alta. Un senzor offline
    produce o singura alerta pana e rezolvata/marcata falsa.
  - reluarea jobului fara senzori noi offline nu schimba nimic.

Conventie offline_timeout_sec:
  - NULL  -> detectie dezactivata pentru senzor (skip).
  - <= 0  -> tratat ca dezactivat (skip) - valoare invalida.
  - > 0   -> senzor offline daca ultima_citire_at < now - timeout.

Senzorii fara nicio citire (ultima_citire_at IS NULL) NU sunt marcati offline:
nu avem o referinta de timp fata de care sa masuram staleness-ul, iar un senzor
proaspat creat care n-a trimis inca nimic nu e "cazut". Devine eligibil dupa
prima citire.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from models import db, Senzor, SensorAlert


_logger = logging.getLogger(__name__)


# Statusurile in care o alerta offline e considerata "inca deschisa" -> de-dup.
# 'falsa' / 'rezolvata' sunt terminale: dupa ele se poate genera o alerta noua
# daca senzorul e (din nou) offline.
_STATUSURI_DESCHISE = ('noua', 'confirmata')


def _alerta_offline_deschisa(senzor_id: int) -> Optional[SensorAlert]:
    """Returneaza o alerta offline deschisa (noua/confirmata) pentru senzor sau None."""
    return (SensorAlert.query
            .filter(SensorAlert.senzor_id == senzor_id,
                    SensorAlert.tip == 'offline',
                    SensorAlert.status.in_(_STATUSURI_DESCHISE))
            .first())


def check_offline(*, now: Optional[datetime] = None,
                  doar_activi: bool = True,
                  commit: bool = True) -> dict:
    """
    Scaneaza senzorii si genereaza alerte 'offline' pentru cei fara citiri
    recente (ultima_citire_at mai veche decat offline_timeout_sec).

    Parametri:
        now          - momentul de referinta (UTC); implicit datetime.utcnow().
                       Injectabil pentru teste deterministe.
        doar_activi  - daca True (implicit), ignora senzorii inactivi.
        commit       - daca True (implicit), face un singur db.session.commit()
                       la final (un write pe SQLite, evita 'database is locked').

    Returneaza un sumar:
        {
            'verificati': N,        # senzori eligibili (timeout setat > 0)
            'offline':     M,       # senzori detectati offline
            'alerte_noi':  K,       # alerte offline create (M minus de-dup)
            'deja_alertat': D,      # senzori offline cu alerta deja deschisa
        }

    Idempotent: de-dup pe alerta offline deschisa per senzor. Reutilizeaza
    dispatch_alert din Faza 1 (gated de flag 'iot-alert-notify'; cu OFF alerta
    se naste tacut, ca restul alertelor).
    """
    if now is None:
        now = datetime.utcnow()

    rezultat = {'verificati': 0, 'offline': 0, 'alerte_noi': 0, 'deja_alertat': 0}

    q = Senzor.query.filter(Senzor.offline_timeout_sec.isnot(None))
    if doar_activi:
        q = q.filter(Senzor.activ.is_(True))

    alerte_noi = []  # SensorAlert-uri create, pentru dispatch dupa flush

    for senzor in q.all():
        timeout = senzor.offline_timeout_sec
        # Valori invalide (<=0) -> tratate ca dezactivat.
        if timeout is None or timeout <= 0:
            continue
        rezultat['verificati'] += 1

        # Fara nicio citire -> nu avem referinta de staleness; nu marcam offline.
        if senzor.ultima_citire_at is None:
            continue

        cutoff = now - timedelta(seconds=int(timeout))
        if senzor.ultima_citire_at >= cutoff:
            continue  # citire recenta -> senzor online

        rezultat['offline'] += 1

        # De-dup: daca exista deja o alerta offline deschisa, nu cream alta.
        if _alerta_offline_deschisa(senzor.id) is not None:
            rezultat['deja_alertat'] += 1
            continue

        secunde_lipsa = int((now - senzor.ultima_citire_at).total_seconds())
        mesaj = (f'{senzor.cod} ({senzor.tip}): fara citiri de {secunde_lipsa}s '
                 f'(prag offline {int(timeout)}s). Ultima citire '
                 f'{senzor.ultima_citire_at.isoformat()}.')[:500]
        alert = SensorAlert(
            tenant_id=senzor.tenant_id,
            senzor_id=senzor.id,
            tip='offline',
            severitate='mare',
            valoare=None,
            threshold_violat=None,
            mesaj=mesaj,
            status='noua',
            data_alerta=now,
        )
        db.session.add(alert)
        alerte_noi.append(alert)
        rezultat['alerte_noi'] += 1

    if alerte_noi:
        db.session.flush()  # asigura id-urile inainte de dispatch

    # Inchide bucla alerta -> notificare, refoloseste Faza 1. commit=False ca sa
    # se uneasca cu commit-ul de mai jos (un singur write). Best-effort: orice
    # eroare e prinsa, nu rupe jobul.
    for alert in alerte_noi:
        try:
            from services import iot_alerting as iot_alerting_svc
            iot_alerting_svc.dispatch_alert(alert, commit=False)
        except Exception as e:
            _logger.warning('check_offline dispatch_alert a esuat: %s', e)

    if commit:
        db.session.commit()

    return rezultat
