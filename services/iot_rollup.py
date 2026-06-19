"""
Rollup + retention pentru time-series IoT (IoT Faza 2).

Problema (audit AUDIT_IOT.md): pentru agg='1h'/'1d', iot_query.get_history
incarca TOATE citirile unui senzor in Python si agrega in memorie. Pe un senzor
cu sute de mii de randuri -> OOM / timeout pe worker-ul PA.

Solutie: materializam agregarea (min/max/avg/count) per (senzor, bucket,
bucket_ts) in tabelul bim_sensor_rollup, populat incremental de CLI
'flask iot-rollup'. iot_query.get_history citeste din rollup cand flag-ul
'iot-rollup' e ON.

Bucketizarea TREBUIE sa fie identica cu cea din iot_query (agregarea Python),
ca rollup-ul sa dea aceleasi valori (echivalenta testata):
  - '1h' -> truncat la ora    (strftime '%Y-%m-%dT%H:00:00')
  - '1d' -> truncat la zi      (strftime '%Y-%m-%d')
  - rotunjire la 4 zecimale pentru min/max/avg.

Incremental + idempotent (watermark cu suprapunere):
  - Reprocesam doar bucket-urile incepand cu ultimul bucket_ts deja materializat
    (per senzor+bucket) minus o fereastra de suprapunere (lookback) pentru
    citiri sosite usor in dezordine. Bucket-urile vechi inchise sunt sarite.
  - UPSERT pe (senzor_id, bucket, bucket_ts) via indexul UNIC -> a 2-a rulare
    nu dubleaza randuri si recalculeaza aceleasi valori.

Retention:
  - cleanup_readings(older_than_days) sterge citirile raw mai vechi de X zile
    (rollup-ul ramane). Bulk DELETE, fara incarcare in Python.
  - cleanup_old_events deleaga la realtime.cleanup_old_events existent.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from models import db, Senzor, SensorReading, SensorRollup


_logger = logging.getLogger(__name__)


# Bucket-urile suportate si formatul de truncare (identic cu iot_query).
_BUCKET_FMT = {
    '1h': '%Y-%m-%dT%H:00:00',
    '1d': '%Y-%m-%d',
}


def _bucket_ts(ts: datetime, bucket: str) -> datetime:
    """Trunchiaza un timestamp la inceputul bucket-ului (ora/zi).

    Acelasi rezultat ca strftime-ul din iot_query, dar intors ca datetime
    (cheia in DB e DateTime, nu string).
    """
    if bucket == '1h':
        return ts.replace(minute=0, second=0, microsecond=0)
    elif bucket == '1d':
        return ts.replace(hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f'bucket invalid: {bucket} (folositi 1h sau 1d)')


def _watermark_de_la(senzor_id: int, bucket: str, lookback_buckets: int) -> Optional[datetime]:
    """Returneaza bucket_ts de la care reprocesam (sau None = de la inceput).

    = ultimul bucket_ts materializat pentru (senzor, bucket), dat inapoi cu
    `lookback_buckets` ferestre (suprapunere pentru citiri usor in dezordine).
    Prima rulare (fara rollup) -> None -> procesam tot istoricul.
    """
    ultim = (db.session.query(db.func.max(SensorRollup.bucket_ts))
             .filter(SensorRollup.senzor_id == senzor_id,
                     SensorRollup.bucket == bucket)
             .scalar())
    if ultim is None:
        return None
    if lookback_buckets <= 0:
        return ultim
    delta = timedelta(hours=lookback_buckets) if bucket == '1h' \
        else timedelta(days=lookback_buckets)
    return ultim - delta


def _upsert_bucket(senzor: Senzor, bucket: str, bucket_ts: datetime,
                   v_min: float, v_max: float, v_avg: float, v_count: int) -> bool:
    """UPSERT un rand de rollup. Returneaza True daca a fost creat (nou)."""
    rand = (SensorRollup.query
            .filter_by(senzor_id=senzor.id, bucket=bucket, bucket_ts=bucket_ts)
            .first())
    creat = False
    if rand is None:
        rand = SensorRollup(
            tenant_id=senzor.tenant_id,
            senzor_id=senzor.id,
            bucket=bucket,
            bucket_ts=bucket_ts,
        )
        db.session.add(rand)
        creat = True
    rand.v_min = round(v_min, 4)
    rand.v_max = round(v_max, 4)
    rand.v_avg = round(v_avg, 4)
    rand.v_count = v_count
    return creat


def rollup_senzor(senzor: Senzor, *,
                  buckets: tuple[str, ...] = ('1h', '1d'),
                  lookback_buckets: int = 1,
                  commit: bool = True) -> dict:
    """
    Materializeaza (incremental) rollup-ul unui senzor pentru bucket-urile date.

    Pentru fiecare bucket ('1h'/'1d'):
      1. Aflam watermark-ul (ultimul bucket_ts deja materializat - lookback).
      2. Recalculam min/max/avg/count din citirile cu ts >= watermark, grupate
         pe bucket (recalcul complet al bucket-ului -> valori corecte chiar daca
         au sosit citiri noi in interior).
      3. UPSERT pe (senzor, bucket, bucket_ts) via indexul UNIC (idempotent).

    Returneaza {'buckets_create': N, 'buckets_update': M, 'citiri_procesate': K}.
    """
    rezultat = {'buckets_create': 0, 'buckets_update': 0, 'citiri_procesate': 0}

    for bucket in buckets:
        if bucket not in _BUCKET_FMT:
            raise ValueError(f'bucket invalid: {bucket} (folositi 1h sau 1d)')

        de_la = _watermark_de_la(senzor.id, bucket, lookback_buckets)

        q = SensorReading.query.filter(SensorReading.senzor_id == senzor.id)
        if de_la is not None:
            q = q.filter(SensorReading.ts >= de_la)
        # Ordonam ca sa procesam determinist (nu strict necesar pentru agregare).
        citiri = q.order_by(SensorReading.ts).all()

        if not citiri:
            continue

        # Agregam in Python DOAR citirile din fereastra (marginita de watermark),
        # nu tot istoricul - exact ce evita OOM-ul global.
        acc: dict[datetime, dict] = {}
        for r in citiri:
            key = _bucket_ts(r.ts, bucket)
            b = acc.setdefault(key, {'min': float('inf'), 'max': float('-inf'),
                                     'sum': 0.0, 'count': 0})
            v = float(r.valoare)
            if v < b['min']:
                b['min'] = v
            if v > b['max']:
                b['max'] = v
            b['sum'] += v
            b['count'] += 1
            rezultat['citiri_procesate'] += 1

        for key, b in acc.items():
            creat = _upsert_bucket(
                senzor, bucket, key,
                v_min=b['min'], v_max=b['max'],
                v_avg=b['sum'] / b['count'], v_count=b['count'],
            )
            if creat:
                rezultat['buckets_create'] += 1
            else:
                rezultat['buckets_update'] += 1

    if commit:
        db.session.commit()
    return rezultat


def rollup_all(*, buckets: tuple[str, ...] = ('1h', '1d'),
               lookback_buckets: int = 1,
               doar_activi: bool = True,
               commit: bool = True) -> dict:
    """
    Ruleaza rollup-ul incremental pentru toti senzorii (activi).

    Apelat de CLI 'flask iot-rollup'. Commit o singura data la final (un write
    pe SQLite). Idempotent: a 2-a rulare fara citiri noi nu schimba nimic.
    """
    q = Senzor.query
    if doar_activi:
        q = q.filter(Senzor.activ.is_(True))
    senzori = q.all()

    total = {'senzori': 0, 'buckets_create': 0, 'buckets_update': 0,
             'citiri_procesate': 0}
    for s in senzori:
        r = rollup_senzor(s, buckets=buckets, lookback_buckets=lookback_buckets,
                          commit=False)
        total['senzori'] += 1
        total['buckets_create'] += r['buckets_create']
        total['buckets_update'] += r['buckets_update']
        total['citiri_procesate'] += r['citiri_procesate']

    if commit:
        db.session.commit()
    return total


# ====================================================
# Retention
# ====================================================

def cleanup_readings(older_than_days: int = 365, *, commit: bool = True) -> int:
    """
    Sterge citirile raw (bim_sensor_readings) mai vechi de X zile.

    Rollup-ul (bim_sensor_rollup) NU e atins - istoricul agregat ramane chiar
    dupa ce citirile raw sunt purjate. Bulk DELETE (fara incarcare in Python).
    Returneaza nr. de randuri sterse.

    older_than_days <= 0 dezactiveaza purjarea (returneaza 0) - retentie
    nelimitata pe readings.
    """
    if older_than_days is None or older_than_days <= 0:
        return 0
    cutoff = datetime.utcnow() - timedelta(days=older_than_days)
    sterse = (SensorReading.query
              .filter(SensorReading.ts < cutoff)
              .delete(synchronize_session=False))
    if commit:
        db.session.commit()
    return sterse


def cleanup_events(older_than_days: int = 7) -> int:
    """
    Deleaga la realtime.cleanup_old_events (sterge bim_realtime_events vechi).

    Centralizat aici ca sa fie un singur punct de retentie pentru CLI
    'flask iot-cleanup'. Returneaza nr. de evenimente sterse.
    """
    from services import realtime as rt_svc
    return rt_svc.cleanup_old_events(older_than_days=older_than_days)
