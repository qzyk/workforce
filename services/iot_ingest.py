"""
Ingest service pentru date IoT.

- Validare token (X-Sensor-Token sau api_key in URL)
- Insert SensorReading + actualizare cache pe Senzor (ultima_valoare, ultima_citire_at)
- Threshold check + auto-creare SensorAlert daca valoarea e in afara range
- Audit log pe alerte (nu pe fiecare reading - too verbose)
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime
from typing import Optional

from models import db, Senzor, SensorReading, SensorAlert
from services import audit as audit_svc


_logger = logging.getLogger(__name__)


# ====================================================
# CRUD senzori
# ====================================================

def _generate_api_key() -> str:
    """Genereaza un token sigur pentru ingest (32 bytes hex = 64 chars)."""
    return secrets.token_hex(32)


def create_senzor(cod: str, nume: str, tip: str, *,
                  unitate: Optional[str] = None,
                  element_bim_id: Optional[int] = None,
                  spatiu_id: Optional[int] = None,
                  cladire_id: Optional[int] = None,
                  threshold_min: Optional[float] = None,
                  threshold_max: Optional[float] = None,
                  descriere: Optional[str] = None,
                  producator: Optional[str] = None,
                  model_hardware: Optional[str] = None,
                  serial: Optional[str] = None,
                  user=None,
                  tenant_id: Optional[int] = None,
                  commit: bool = True) -> Senzor:
    """Creeaza un senzor nou cu API key generat automat."""
    if not cod or not nume:
        raise ValueError('Cod si nume sunt obligatorii')
    if tip not in [t[0] for t in Senzor.TIPURI]:
        raise ValueError(f'Tip invalid: {tip}')
    # Cel putin un location FK
    if not (element_bim_id or spatiu_id or cladire_id):
        raise ValueError('Senzorul trebuie atasat unui element / spatiu / cladire')

    if unitate is None:
        unitate = Senzor.UNITATI_DEFAULT.get(tip, '-')

    s = Senzor(
        tenant_id=tenant_id,
        cod=cod.strip(),
        nume=nume.strip(),
        tip=tip,
        unitate=unitate,
        element_bim_id=element_bim_id,
        spatiu_id=spatiu_id,
        cladire_id=cladire_id,
        threshold_min=threshold_min,
        threshold_max=threshold_max,
        descriere=(descriere or '').strip() or None,
        producator=(producator or '').strip() or None,
        model_hardware=(model_hardware or '').strip() or None,
        serial=(serial or '').strip() or None,
        api_key=_generate_api_key(),
        activ=True,
        creat_de_id=getattr(user, 'id', None) if user else None,
    )
    db.session.add(s)
    db.session.flush()
    audit_svc.log_create('bim_senzor', s.id, new_values={
        'cod': cod, 'nume': nume, 'tip': tip,
        'element_bim_id': element_bim_id, 'spatiu_id': spatiu_id,
    })
    if commit:
        db.session.commit()
    return s


def rotate_api_key(senzor: Senzor, *, commit: bool = True) -> str:
    """Roteaza token-ul (invalideaza cel vechi). Returneaza noul token."""
    old_key_prefix = senzor.api_key[:8] if senzor.api_key else None
    senzor.api_key = _generate_api_key()
    audit_svc.log('rotate_api_key', 'bim_senzor', senzor.id,
                  old_values={'api_key_prefix': old_key_prefix},
                  new_values={'api_key_prefix': senzor.api_key[:8]})
    if commit:
        db.session.commit()
    return senzor.api_key


# ====================================================
# Ingest
# ====================================================

def authenticate_token(token: str) -> Optional[Senzor]:
    """
    Returneaza Senzor pentru token-ul dat sau None.
    Token-ul trebuie sa aiba 64 hex chars.
    """
    if not token or len(token) < 16:
        return None
    return Senzor.query.filter_by(api_key=token, activ=True).first()


def ingest_reading(senzor: Senzor, valoare: float, *,
                   ts: Optional[datetime] = None,
                   calitate: str = 'ok',
                   meta: Optional[dict] = None,
                   commit: bool = True) -> dict:
    """
    Insereaza o citire + verifica threshold + genereaza alert daca e nevoie.

    Returneaza:
        {
            'reading_id': X,
            'alert_created': True/False,
            'alert_id': Y or None,
            'threshold_violated': 'sub_min' | 'peste_max' | None,
        }
    """
    if ts is None:
        ts = datetime.utcnow()
    if calitate not in ('ok', 'estimat', 'eroare', 'maintenance'):
        calitate = 'ok'

    # Insert reading
    reading = SensorReading(
        tenant_id=senzor.tenant_id,
        senzor_id=senzor.id,
        ts=ts,
        valoare=valoare,
        calitate=calitate,
        meta_json=json.dumps(meta, ensure_ascii=False) if meta else None,
    )
    db.session.add(reading)
    db.session.flush()

    # Update cache pe senzor (ultima valoare)
    senzor.ultima_valoare = valoare
    senzor.ultima_citire_at = ts

    # Threshold check
    alert_id = None
    violation = None
    alert_obj = None       # SensorAlert generat/escaladat (pentru dispatch notificare)
    alert_escaladat = False  # True daca o alerta existenta a crescut in severitate
    if calitate == 'ok' and senzor.threshold_min is not None and valoare < float(senzor.threshold_min):
        violation = 'sub_min'
    elif calitate == 'ok' and senzor.threshold_max is not None and valoare > float(senzor.threshold_max):
        violation = 'peste_max'

    if violation:
        # Severitate: cu cat depaseste mai mult, cu atat e mai grav
        if violation == 'sub_min':
            ratio = (float(senzor.threshold_min) - valoare) / max(abs(float(senzor.threshold_min)), 1)
        else:
            ratio = (valoare - float(senzor.threshold_max)) / max(abs(float(senzor.threshold_max)), 1)

        if ratio > 0.5:
            severitate = 'critica'
        elif ratio > 0.2:
            severitate = 'mare'
        else:
            severitate = 'medie'

        threshold_val = (float(senzor.threshold_min) if violation == 'sub_min'
                         else float(senzor.threshold_max))

        # Verific daca exista deja alert deschis pentru acelasi tip violation
        # (ca sa nu spamuim; doar update daca e mai severa)
        existing = SensorAlert.query.filter_by(
            senzor_id=senzor.id, tip=violation, status='noua').first()

        if existing:
            # Update doar daca noua e mai severa
            severitati_order = ['mica', 'medie', 'mare', 'critica']
            if severitati_order.index(severitate) > severitati_order.index(existing.severitate):
                existing.severitate = severitate
                existing.valoare = valoare
                existing.mesaj = (f'{senzor.cod}: valoare {valoare}{senzor.unitate} '
                                  f'iese din threshold ({violation}: {threshold_val})')
                # Escaladare: re-notificam (vezi dispatch mai jos).
                alert_escaladat = True
                alert_obj = existing
            alert_id = existing.id
        else:
            alert = SensorAlert(
                tenant_id=senzor.tenant_id,
                senzor_id=senzor.id,
                tip=violation,
                severitate=severitate,
                valoare=valoare,
                threshold_violat=threshold_val,
                mesaj=(f'{senzor.cod} ({senzor.tip}): valoare {valoare}{senzor.unitate} '
                       f'iese din threshold {violation} ({threshold_val})')[:500],
                status='noua',
                data_alerta=ts,
            )
            db.session.add(alert)
            db.session.flush()
            alert_id = alert.id
            alert_obj = alert

            # Audit pe alerta noua (NU pe fiecare reading - too verbose)
            audit_svc.log('sensor_alert_created', 'bim_sensor_alert', alert.id,
                          new_values={
                              'senzor_id': senzor.id, 'senzor_cod': senzor.cod,
                              'tip': violation, 'severitate': severitate,
                              'valoare': valoare, 'threshold': threshold_val,
                          })

    # IoT Faza 1: inchide bucla alerta -> notificare. Doar la alerta noua sau
    # escaladata. dispatch_alert e gated de flag 'iot-alert-notify' (default OFF);
    # cu OFF e no-op (zero notificari, comportament istoric). commit=False ca sa
    # se uneasca cu commit-ul de mai jos (un singur write pe SQLite). Best-effort:
    # orice eroare e prinsa, nu rupe ingestul.
    if alert_obj is not None:
        try:
            from services import iot_alerting as iot_alerting_svc
            iot_alerting_svc.dispatch_alert(
                alert_obj, escalada=alert_escaladat, commit=False)
        except Exception as e:
            _logger.warning('ingest_reading dispatch_alert a esuat: %s', e)

    if commit:
        db.session.commit()

    return {
        'reading_id': reading.id,
        'ts': ts.isoformat(),
        'alert_created': alert_id is not None,
        'alert_id': alert_id,
        'threshold_violated': violation,
    }


def ingest_batch(senzor: Senzor, readings: list, *,
                 commit: bool = True) -> dict:
    """
    Insereaza un LOT de citiri pentru un senzor cu un SINGUR commit (IoT Faza 3).

    Rezolva MINOR-ul din audit (commit per-request serializeaza scrierile pe
    SQLite -> 'database is locked' la volum). Fiecare element din `readings`
    e procesat prin ingest_reading(commit=False); commit-ul se face o singura
    data la final. Threshold check + de-dup alerte + dispatch notificare se
    pastreaza identic (un singur write pe lot).

    Parametri:
        senzor   - senzorul autentificat (acelasi pentru tot lotul).
        readings - lista de dict-uri: {'valoare': float (obligatoriu),
                   'ts': ISO str / datetime (opt), 'calitate': str (opt),
                   'meta': dict (opt)}.
        commit   - daca True (implicit), un singur db.session.commit() la final.

    Returneaza:
        {
            'ingested': N,           # citiri inserate cu succes
            'alerts_created': M,     # alerte noi generate in lot
            'errors': [ {idx, error}, ... ],   # elemente respinse (validare)
            'results': [ <result ingest_reading>, ... ],  # per element OK
        }

    Elementele invalide (lipsa 'valoare', valoare ne-numerica, ts invalid) sunt
    raportate in 'errors' fara a rupe restul lotului. Daca un singur element
    valid e procesat, citirile lui intra in acelasi commit cu celelalte.
    """
    rezultat = {'ingested': 0, 'alerts_created': 0, 'errors': [], 'results': []}

    if not isinstance(readings, list):
        raise ValueError('readings trebuie sa fie o lista')

    for idx, item in enumerate(readings):
        if not isinstance(item, dict) or 'valoare' not in item:
            rezultat['errors'].append({'idx': idx, 'error': 'campul valoare e obligatoriu'})
            continue
        try:
            valoare = float(item['valoare'])
        except (ValueError, TypeError):
            rezultat['errors'].append({'idx': idx, 'error': 'valoare trebuie sa fie numerica'})
            continue

        ts = item.get('ts')
        if ts is not None and not isinstance(ts, datetime):
            try:
                ts = datetime.fromisoformat(str(ts).rstrip('Z'))
            except (ValueError, TypeError):
                rezultat['errors'].append({'idx': idx, 'error': 'ts invalid; folositi ISO 8601'})
                continue

        # commit=False: toate citirile lotului intra intr-un singur write.
        res = ingest_reading(
            senzor, valoare,
            ts=ts,
            calitate=item.get('calitate', 'ok'),
            meta=item.get('meta'),
            commit=False,
        )
        rezultat['results'].append(res)
        rezultat['ingested'] += 1
        if res.get('alert_created'):
            rezultat['alerts_created'] += 1

    if commit:
        db.session.commit()

    return rezultat


# ====================================================
# Alert workflow
# ====================================================

def transition_alert(alert: SensorAlert, new_status: str, user, *,
                     commit: bool = True) -> SensorAlert:
    """
    Schimba status-ul unui alert (noua -> confirmata / falsa -> rezolvata).
    """
    valid_transitions = {
        'noua':       {'confirmata', 'falsa', 'rezolvata'},
        'confirmata': {'rezolvata', 'falsa'},
        'falsa':      set(),
        'rezolvata':  set(),
    }
    if new_status not in valid_transitions.get(alert.status, set()):
        raise ValueError(
            f'Tranzitie invalida: {alert.status} -> {new_status}'
        )

    old_status = alert.status
    alert.status = new_status
    now = datetime.utcnow()
    if new_status == 'confirmata':
        alert.data_confirmare = now
        alert.confirmat_de_id = getattr(user, 'id', None) if user else None
    elif new_status == 'rezolvata':
        alert.data_rezolvare = now

    audit_svc.log('sensor_alert_transition', 'bim_sensor_alert', alert.id,
                  old_values={'status': old_status},
                  new_values={'status': new_status})

    if commit:
        db.session.commit()
    return alert
