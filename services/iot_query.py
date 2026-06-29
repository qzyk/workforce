"""
Query service pentru date IoT.

- current_state(element/spatiu/cladire) — ultimele citiri
- history(senzor_id, from, to, agg) — time-series cu agregare optionala
- aggregate(senzor_id, agg='1h'|'1d') — min/max/avg per perioada
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func

from models import db, Senzor, SensorReading, SensorAlert


# ====================================================
# Current state
# ====================================================

def get_current_state_element(element_bim_id: int, tenant_id: Optional[int] = None) -> dict:
    """
    Returneaza ultimele citiri ale tuturor senzorilor atasati la element.
    """
    from services.security.tenant_access import query_sensors_for_tenant

    senzori = query_sensors_for_tenant(tenant_id=tenant_id).filter_by(
        element_bim_id=element_bim_id,
        activ=True,
    ).all()
    return {
        'element_bim_id': element_bim_id,
        'count_sensors': len(senzori),
        'sensors': [_senzor_summary(s) for s in senzori],
    }


def get_current_state_spatiu(spatiu_id: int, tenant_id: Optional[int] = None) -> dict:
    from services.security.tenant_access import query_sensors_for_tenant

    senzori = query_sensors_for_tenant(tenant_id=tenant_id).filter_by(
        spatiu_id=spatiu_id,
        activ=True,
    ).all()
    return {
        'spatiu_id': spatiu_id,
        'count_sensors': len(senzori),
        'sensors': [_senzor_summary(s) for s in senzori],
    }


def get_current_state_cladire(cladire_id: int, tenant_id: Optional[int] = None) -> dict:
    """Toate senzorii din cladire (direct + via spatii din cladire)."""
    from models import Nivel, Spatiu
    from services.security.tenant_access import (
        query_bim_levels_for_tenant,
        query_bim_spaces_for_tenant,
        query_sensors_for_tenant,
    )

    senzori_direct = query_sensors_for_tenant(tenant_id=tenant_id).filter_by(
        cladire_id=cladire_id,
        activ=True,
    ).all()
    # + senzorii pe spatii din aceasta cladire
    nivel_ids = [
        n.id for n in query_bim_levels_for_tenant(tenant_id=tenant_id)
        .filter_by(cladire_id=cladire_id).all()
    ]
    spatiu_ids = [
        s.id for s in query_bim_spaces_for_tenant(tenant_id=tenant_id)
        .filter(Spatiu.nivel_id.in_(nivel_ids)).all()
    ]
    senzori_pe_spatii = query_sensors_for_tenant(tenant_id=tenant_id).filter(
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

def get_history(senzor_id: int, *,
                from_ts: Optional[datetime] = None,
                to_ts: Optional[datetime] = None,
                agg: str = 'raw',
                limit: int = 5000,
                tenant_id: Optional[int] = None) -> dict:
    """
    Returneaza istoricul citirilor pentru un senzor.

    agg:
        'raw' - toate citirile (limitat la limit, default 5000)
        '1h'  - agregare pe ore (min, max, avg per ora)
        '1d'  - agregare pe zile

    Pentru agregare folosim SQL group by pe truncated timestamp.
    """
    if from_ts is None:
        from_ts = datetime.utcnow() - timedelta(days=7)
    if to_ts is None:
        to_ts = datetime.utcnow()

    from services.security.tenant_access import (
        get_sensor_or_404,
        query_sensor_readings_for_tenant,
    )

    senzor = get_sensor_or_404(senzor_id, tenant_id=tenant_id)
    base_q = query_sensor_readings_for_tenant(
        sensor_id=senzor.id,
        tenant_id=tenant_id,
    ).filter(
        SensorReading.ts >= from_ts,
        SensorReading.ts <= to_ts,
    )

    if agg == 'raw':
        readings = base_q.order_by(SensorReading.ts).limit(limit).all()
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

    # Agregare: in functie de dialect, folosim DATE_TRUNC sau strftime
    # Pentru SQLite: strftime; pentru MySQL: DATE_FORMAT.
    # Implementare portable: incarcam toate citirile si agregam in Python.
    # (Pentru volume mari pe MySQL, se poate inlocui cu DATE_FORMAT GROUP BY.)
    readings = base_q.order_by(SensorReading.ts).all()

    # Agregare in Python pe bucket
    if agg == '1h':
        bucket_fmt = '%Y-%m-%dT%H:00:00'
    elif agg == '1d':
        bucket_fmt = '%Y-%m-%d'
    else:
        raise ValueError(f'agg invalid: {agg} (folositi raw, 1h sau 1d)')

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

    data = [
        {'ts': key,
         'min': round(b['min'], 4),
         'max': round(b['max'], 4),
         'avg': round(b['sum'] / b['count'], 4),
         'count': b['count']}
        for key, b in sorted(buckets.items())
    ]
    return {
        'senzor_id': senzor_id,
        'agg': agg,
        'from': from_ts.isoformat(),
        'to': to_ts.isoformat(),
        'count': len(data),
        'data': data,
    }


def get_active_alerts(*, senzor_id: Optional[int] = None,
                      tenant_id: Optional[int] = None,
                      limit: int = 200) -> list[SensorAlert]:
    """Returneaza alertele cu status='noua' sau 'confirmata'."""
    from services.security.tenant_access import query_sensor_alerts_for_tenant

    q = query_sensor_alerts_for_tenant(
        sensor_id=senzor_id,
        tenant_id=tenant_id,
    ).filter(SensorAlert.status.in_(['noua', 'confirmata']))
    return q.order_by(SensorAlert.data_alerta.desc()).limit(limit).all()
