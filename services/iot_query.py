"""
Query service pentru date IoT.

- current_state(element/spatiu/cladire) — ultimele citiri
- history(senzor_id, from, to, agg) — time-series cu agregare optionala
- aggregate(senzor_id, agg='1h'|'1d') — min/max/avg per perioada
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from models import Senzor, SensorReading, SensorAlert


# ====================================================
# Current state
# ====================================================

def get_current_state_element(element_bim_id: int) -> dict:
    """
    Returneaza ultimele citiri ale tuturor senzorilor atasati la element.
    """
    senzori = Senzor.query.filter_by(element_bim_id=element_bim_id, activ=True).all()
    return {
        'element_bim_id': element_bim_id,
        'count_sensors': len(senzori),
        'sensors': [_senzor_summary(s) for s in senzori],
    }


def get_current_state_spatiu(spatiu_id: int) -> dict:
    senzori = Senzor.query.filter_by(spatiu_id=spatiu_id, activ=True).all()
    return {
        'spatiu_id': spatiu_id,
        'count_sensors': len(senzori),
        'sensors': [_senzor_summary(s) for s in senzori],
    }


def get_current_state_cladire(cladire_id: int) -> dict:
    """Toate senzorii din cladire (direct + via spatii din cladire)."""
    senzori_direct = Senzor.query.filter_by(cladire_id=cladire_id, activ=True).all()
    # + senzorii pe spatii din aceasta cladire
    from models import Spatiu, Nivel
    nivel_ids = [n.id for n in Nivel.query.filter_by(cladire_id=cladire_id).all()]
    spatiu_ids = [s.id for s in Spatiu.query.filter(Spatiu.nivel_id.in_(nivel_ids)).all()]
    senzori_pe_spatii = Senzor.query.filter(
        Senzor.spatiu_id.in_(spatiu_ids), Senzor.activ.is_(True)
    ).all() if spatiu_ids else []
    all_senzori = senzori_direct + senzori_pe_spatii
    return {
        'cladire_id': cladire_id,
        'count_sensors': len(all_senzori),
        'sensors': [_senzor_summary(s) for s in all_senzori],
    }


def _senzor_summary(s: Senzor) -> dict:
    """Helper: rezumat senzor pentru API."""
    return {
        'id': s.id,
        'cod': s.cod,
        'nume': s.nume,
        'tip': s.tip,
        'label_tip': s.label_tip,
        'unitate': s.unitate,
        'ultima_valoare': float(s.ultima_valoare) if s.ultima_valoare is not None else None,
        'ultima_citire_at': s.ultima_citire_at.isoformat() if s.ultima_citire_at else None,
        'threshold_min': float(s.threshold_min) if s.threshold_min is not None else None,
        'threshold_max': float(s.threshold_max) if s.threshold_max is not None else None,
        'is_alarming': s.is_alarming,
    }


# ====================================================
# History
# ====================================================

# Sub aceasta fereastra (in ore), agregarea 1h/1d ramane in Python chiar cu
# flag-ul 'iot-rollup' ON - acopera bucket-ul curent (inca deschis), care nu e
# inca materializat de CLI-ul incremental.
_PRAG_FALLBACK_ORE = 24


def get_history(senzor_id: int, *,
                from_ts: Optional[datetime] = None,
                to_ts: Optional[datetime] = None,
                agg: str = 'raw',
                limit: int = 5000) -> dict:
    """
    Returneaza istoricul citirilor pentru un senzor.

    agg:
        'raw' - toate citirile (limitat la limit, default 5000)
        '1h'  - agregare pe ore (min, max, avg per ora)
        '1d'  - agregare pe zile

    IoT Faza 2: pentru agg='1h'/'1d', daca flag-ul 'iot-rollup' e ON SI fereastra
    >= 24h, citim agregarea pre-calculata din bim_sensor_rollup (scalabil, nu
    incarca toate citirile in Python). Pe ferestre < 24h sau cu flag OFF ramane
    agregarea live in Python (comportament istoric, neschimbat).
    """
    if from_ts is None:
        from_ts = datetime.utcnow() - timedelta(days=7)
    if to_ts is None:
        to_ts = datetime.utcnow()

    if agg == 'raw':
        readings = (SensorReading.query.filter(
            SensorReading.senzor_id == senzor_id,
            SensorReading.ts >= from_ts,
            SensorReading.ts <= to_ts,
        ).order_by(SensorReading.ts).limit(limit).all())
        return {
            'senzor_id': senzor_id,
            'agg': 'raw',
            'from': from_ts.isoformat(),
            'to': to_ts.isoformat(),
            'count': len(readings),
            'data': [
                {'ts': r.ts.isoformat(), 'valoare': float(r.valoare),
                 'calitate': r.calitate}
                for r in readings
            ],
        }

    if agg not in ('1h', '1d'):
        raise ValueError(f'agg invalid: {agg} (folositi raw, 1h sau 1d)')

    # Decizie sursa: rollup (scalabil) vs. agregare Python (live).
    fereastra_ore = (to_ts - from_ts).total_seconds() / 3600.0
    if fereastra_ore >= _PRAG_FALLBACK_ORE and _rollup_activ(senzor_id):
        data = _history_din_rollup(senzor_id, from_ts, to_ts, agg)
    else:
        data = _history_din_readings(senzor_id, from_ts, to_ts, agg)

    return {
        'senzor_id': senzor_id,
        'agg': agg,
        'from': from_ts.isoformat(),
        'to': to_ts.isoformat(),
        'count': len(data),
        'data': data,
    }


def _rollup_activ(senzor_id: int) -> bool:
    """True daca flag-ul 'iot-rollup' e ON pentru tenant-ul senzorului."""
    try:
        from services import feature_flags as ff_svc
        senzor = Senzor.query.get(senzor_id)
        tenant_id = senzor.tenant_id if senzor is not None else None
        return ff_svc.is_enabled('iot-rollup', tenant_id=tenant_id)
    except Exception:
        return False


def _history_din_rollup(senzor_id: int, from_ts: datetime, to_ts: datetime,
                        agg: str) -> list[dict]:
    """Citeste agregarea pre-calculata din bim_sensor_rollup.

    Formatul cheii 'ts' e identic cu cel din agregarea Python (strftime), ca
    rezultatul sa fie echivalent (vezi teste).
    """
    from models import SensorRollup
    bucket_fmt = '%Y-%m-%dT%H:00:00' if agg == '1h' else '%Y-%m-%d'
    randuri = (SensorRollup.query.filter(
        SensorRollup.senzor_id == senzor_id,
        SensorRollup.bucket == agg,
        SensorRollup.bucket_ts >= from_ts,
        SensorRollup.bucket_ts <= to_ts,
    ).order_by(SensorRollup.bucket_ts).all())
    return [
        {'ts': r.bucket_ts.strftime(bucket_fmt),
         'min': float(r.v_min) if r.v_min is not None else None,
         'max': float(r.v_max) if r.v_max is not None else None,
         'avg': float(r.v_avg) if r.v_avg is not None else None,
         'count': r.v_count}
        for r in randuri
    ]


def _history_din_readings(senzor_id: int, from_ts: datetime, to_ts: datetime,
                          agg: str) -> list[dict]:
    """Agregare live in Python pe citirile raw (comportament istoric).

    Implementare portable cross-dialect (SQLite/MySQL). Pentru volume mari pe
    ferestre lungi se foloseste rollup-ul (vezi get_history). Bucketizarea e
    identica cu cea din services/iot_rollup ca sursele sa fie echivalente.
    """
    readings = SensorReading.query.filter(
        SensorReading.senzor_id == senzor_id,
        SensorReading.ts >= from_ts,
        SensorReading.ts <= to_ts,
    ).order_by(SensorReading.ts).all()

    bucket_fmt = '%Y-%m-%dT%H:00:00' if agg == '1h' else '%Y-%m-%d'

    buckets: dict = {}
    for r in readings:
        key = r.ts.strftime(bucket_fmt)
        b = buckets.setdefault(key, {'min': float('inf'), 'max': float('-inf'),
                                      'sum': 0, 'count': 0})
        v = float(r.valoare)
        if v < b['min']: b['min'] = v
        if v > b['max']: b['max'] = v
        b['sum'] += v
        b['count'] += 1

    return [
        {'ts': key,
         'min': round(b['min'], 4),
         'max': round(b['max'], 4),
         'avg': round(b['sum'] / b['count'], 4),
         'count': b['count']}
        for key, b in sorted(buckets.items())
    ]


def get_active_alerts(*, senzor_id: Optional[int] = None,
                      tenant_id: Optional[int] = None,
                      limit: int = 200) -> list[SensorAlert]:
    """Returneaza alertele cu status='noua' sau 'confirmata'."""
    q = SensorAlert.query.filter(SensorAlert.status.in_(['noua', 'confirmata']))
    if senzor_id:
        q = q.filter_by(senzor_id=senzor_id)
    if tenant_id:
        q = q.filter_by(tenant_id=tenant_id)
    return q.order_by(SensorAlert.data_alerta.desc()).limit(limit).all()
