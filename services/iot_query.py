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
    >= 24h SI rollup-ul acopera fereastra, citim agregarea pre-calculata din
    bim_sensor_rollup (scalabil, nu incarca toate citirile in Python). Pe ferestre
    < 24h, cu flag OFF, SAU cand rollup-ul e gol / in urma (cron neconfigurat,
    senzor proaspat backfilled) ramane agregarea live in Python (comportament
    istoric). Flag-ul si cron-ul fiind independente, NU presupunem ca rollup-ul e
    populat: daca nu acopera fereastra, cadem pe Python (vezi _rollup_acopera) ca
    sa nu intoarcem o serie trunchiata (chart gol). Asta pastreaza garantia ca
    pornirea flag-ului ON nu schimba valorile.

    Echivalenta exacta: rezultatul ramurii rollup e identic cu agregarea Python
    pe ORICE fereastra, inclusiv cand from_ts/to_ts cad in mijlocul unui bucket -
    bucket-urile de margine partiale sunt reconciliate din citirile raw clipuite
    la fereastra (vezi _history_din_rollup). Deci comutarea flag-ului 'iot-rollup'
    ON/OFF nu schimba valorile (doar sursa/performanta).
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
    # Conditii cumulate pentru ramura rollup: flag ON + fereastra >= 24h + rollup
    # acopera fereastra (altfel serie trunchiata -> cadem pe Python).
    fereastra_ore = (to_ts - from_ts).total_seconds() / 3600.0
    if (fereastra_ore >= _PRAG_FALLBACK_ORE
            and _rollup_activ(senzor_id)
            and _rollup_acopera(senzor_id, from_ts, to_ts, agg)):
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


def _rollup_acopera(senzor_id: int, from_ts: datetime, to_ts: datetime,
                    agg: str) -> bool:
    """True daca rollup-ul acopera INTERIORUL ferestrei (e la zi pentru senzor).

    Flag-ul 'iot-rollup' (citire) si cron-ul 'flask iot-rollup' (populare) sunt
    independente. Daca rollup-ul e gol sau in urma, _history_din_rollup ar servi
    interiorul trunchiat (doar marginile recalculate din raw) -> chart gol/partial
    la pornirea flag-ului. Garda: ramura rollup se foloseste DOAR daca rollup-ul e
    la zi pentru acest senzor.

    Definitie acoperire (ieftina + corecta cu rollup_senzor care proceseaza TOATE
    bucket-urile atinse, fara goluri de lookback): rollup-ul e la zi daca bucket-ul
    celei mai recente citiri INTERIOARE (bucket complet inchis in fereastra) are un
    rand in bim_sensor_rollup. Daca cron-ul e in urma, exact bucket-urile interioare
    cele mai noi lipsesc -> verificarea ultimei le prinde. Daca nu exista niciun
    bucket interior (fereastra cade integral pe margini), acoperirea e triviala:
    ramura rollup oricum reconciliaza marginile din raw -> identic cu Python.

    Returneaza True si cand nu exista nicio citire in fereastra (ambele ramuri dau
    serie goala -> echivalente; lasam ramura rollup, ieftina).
    """
    from models import SensorRollup

    pas = _bucket_pas(agg)
    # Cea mai recenta citire INTERIOARA: ts intr-un bucket complet inchis in
    # fereastra (bucket_start >= from_ts SI bucket_start + pas <= to_ts). Marginim
    # ts la [from_ts, ultim_bucket_interior_start + pas) ca sa excludem coada.
    ultim_interior_start = _bucket_start(to_ts, agg)
    if ultim_interior_start + pas > to_ts:
        # bucket-ul care contine to_ts e partial (coada) -> interiorul se termina
        # cu bucket-ul anterior.
        ultim_interior_start = ultim_interior_start - pas

    prim_interior_start = _bucket_start(from_ts, agg)
    if prim_interior_start < from_ts:
        # bucket-ul care contine from_ts e partial (cap) -> interiorul incepe cu
        # bucket-ul urmator.
        prim_interior_start = prim_interior_start + pas

    if ultim_interior_start < prim_interior_start:
        # Nu exista bucket interior complet (fereastra integral pe margini).
        return True

    # Cea mai recenta citire din zona interioara [prim_interior_start, ultim+pas).
    ultim_ts = (SensorReading.query
                .with_entities(SensorReading.ts)
                .filter(SensorReading.senzor_id == senzor_id,
                        SensorReading.ts >= prim_interior_start,
                        SensorReading.ts < ultim_interior_start + pas)
                .order_by(SensorReading.ts.desc())
                .first())
    if ultim_ts is None:
        # Nicio citire interioara -> interiorul e gol in ambele ramuri.
        return True

    bucket_ultim = _bucket_start(ultim_ts[0], agg)
    exista = (SensorRollup.query
              .filter(SensorRollup.senzor_id == senzor_id,
                      SensorRollup.bucket == agg,
                      SensorRollup.bucket_ts == bucket_ultim)
              .first())
    return exista is not None


def _bucket_start(ts: datetime, agg: str) -> datetime:
    """Inceputul bucket-ului care contine ts (truncare la ora/zi).

    Identic cu _bucket_ts din services/iot_rollup (acolo e cheia in DB).
    """
    if agg == '1h':
        return ts.replace(minute=0, second=0, microsecond=0)
    return ts.replace(hour=0, minute=0, second=0, microsecond=0)


def _bucket_pas(agg: str) -> timedelta:
    """Latimea unui bucket (1 ora / 1 zi)."""
    return timedelta(hours=1) if agg == '1h' else timedelta(days=1)


def _agrega_raw_in_bucket(senzor_id: int, bucket_start: datetime,
                          lo: datetime, hi: datetime, agg: str) -> Optional[dict]:
    """Agrega citirile raw ale UNUI bucket, clipuite la fereastra [lo, hi].

    Folosit pentru bucket-urile de margine (partiale) ale ferestrei, ca sa imite
    exact clipping-ul din _history_din_readings (ts >= lo AND ts <= hi). Bucket-ul
    e marginit suplimentar la [bucket_start, bucket_start+pas) ca sa nu prinda
    citiri din bucket-urile vecine. Returneaza None daca nu cade nicio citire
    (bucket absent, exact ca in Python).

    Citire bounded: un singur bucket, nu tot istoricul -> nu reintroduce OOM-ul.
    """
    bucket_end = bucket_start + _bucket_pas(agg)
    lo_ef = max(lo, bucket_start)
    hi_ef = min(hi, bucket_end - timedelta(microseconds=1))
    if lo_ef > hi_ef:
        return None
    readings = SensorReading.query.filter(
        SensorReading.senzor_id == senzor_id,
        SensorReading.ts >= lo_ef,
        SensorReading.ts <= hi_ef,
    ).all()
    if not readings:
        return None
    bucket_fmt = '%Y-%m-%dT%H:00:00' if agg == '1h' else '%Y-%m-%d'
    v_min = float('inf'); v_max = float('-inf'); v_sum = 0.0; v_count = 0
    for r in readings:
        v = float(r.valoare)
        if v < v_min: v_min = v
        if v > v_max: v_max = v
        v_sum += v
        v_count += 1
    return {'ts': bucket_start.strftime(bucket_fmt),
            'min': round(v_min, 4),
            'max': round(v_max, 4),
            'avg': round(v_sum / v_count, 4),
            'count': v_count}


def _history_din_rollup(senzor_id: int, from_ts: datetime, to_ts: datetime,
                        agg: str) -> list[dict]:
    """Citeste agregarea pre-calculata din bim_sensor_rollup, echivalent cu Python.

    Problema marginilor: rollup-ul stocheaza agregarea bucket-ului INTREG. Daca
    fereastra [from_ts, to_ts] taie prin mijlocul unui bucket, agregarea intreaga
    NU coincide cu agregarea partiala pe care _history_din_readings o calculeaza
    (Python clipuieste citirile la fereastra). Doua divergente daca am filtra naiv
    pe bucket_ts in [from_ts, to_ts]:
      (a) un bucket de inceput cu bucket_ts < from_ts dar cu citiri in fereastra
          ar fi pierdut (Python il pastreaza partial);
      (b) un bucket de coada cu bucket_ts <= to_ts dar cu citiri DUPA to_ts ar
          fi raportat intreg (Python nu il are, sau il are partial).

    Solutie (echivalenta exacta cu Python pe ORICE fereastra):
      - bucket-urile complet acoperite de fereastra
        (bucket_start >= from_ts SI bucket_end <= to_ts) vin din rollup (ieftin);
      - cele (cel mult doua) bucket-uri de margine pe care fereastra le taie sunt
        recalculate din citirile raw clipuite la fereastra (citire bounded: 1-2
        bucket-uri, nu tot istoricul) -> rezultat identic cu _history_din_readings.

    Formatul cheii 'ts' e identic cu agregarea Python (strftime).
    """
    from models import SensorRollup

    bucket_fmt = '%Y-%m-%dT%H:00:00' if agg == '1h' else '%Y-%m-%d'
    pas = _bucket_pas(agg)
    start_margine = _bucket_start(from_ts, agg)   # bucket care contine from_ts
    end_margine = _bucket_start(to_ts, agg)       # bucket care contine to_ts

    rezultat: dict[str, dict] = {}

    # 1) Interior: bucket-uri COMPLET in fereastra -> din rollup (scalabil).
    #    bucket_start >= from_ts (deci start_margine inclus doar daca from_ts cade
    #    fix pe granita) SI bucket_start + pas <= to_ts (coada partiala exclusa).
    randuri = (SensorRollup.query.filter(
        SensorRollup.senzor_id == senzor_id,
        SensorRollup.bucket == agg,
        SensorRollup.bucket_ts >= from_ts,
        SensorRollup.bucket_ts <= to_ts - pas,
    ).order_by(SensorRollup.bucket_ts).all())
    for r in randuri:
        rezultat[r.bucket_ts.strftime(bucket_fmt)] = {
            'ts': r.bucket_ts.strftime(bucket_fmt),
            'min': float(r.v_min) if r.v_min is not None else None,
            'max': float(r.v_max) if r.v_max is not None else None,
            'avg': float(r.v_avg) if r.v_avg is not None else None,
            'count': r.v_count,
        }

    # 2) Margini: bucket-ul de inceput si cel de coada (daca fereastra le taie)
    #    se recalculeaza din raw, clipuit la fereastra -> identic cu Python.
    for marg in {start_margine, end_margine}:
        b = _agrega_raw_in_bucket(senzor_id, marg, from_ts, to_ts, agg)
        if b is not None:
            rezultat[b['ts']] = b

    return [rezultat[k] for k in sorted(rezultat)]


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
