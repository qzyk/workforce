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

Incremental + idempotent (watermark pe INSERARE, nu pe timpul masurarii):
  - Watermark-ul per senzor e `Senzor.last_rollup_at` (wall-clock UTC al ultimei
    rulari). La urmatoarea rulare reprocesam DOAR bucket-urile atinse de citiri
    nou-inserate (`SensorReading.created_at > last_rollup_at`) si recalculam
    fiecare astfel de bucket din TOATE citirile lui (recompute complet -> valori
    corecte). Astfel o citire late ingestata (iot_ingest accepta ts explicit,
    backdatat) intr-un bucket vechi DEJA inchis e prinsa: created_at-ul ei e
    recent chiar daca ts-ul e vechi, deci re-rularea o recupereaza. Asta repara
    echivalenta rollup==Python pentru citiri in dezordine de ORICE varsta (nu doar
    in fereastra de lookback, care nu mai exista).
  - UPSERT pe (senzor_id, bucket, bucket_ts) via indexul UNIC -> a 2-a rulare
    nu dubleaza randuri si recalculeaza aceleasi valori.
  - Rebuild complet: rollup_senzor(full=True) / 'flask iot-rollup --full' ignora
    watermark-ul si reproceseaza tot istoricul. Util pentru randuri vechi fara
    created_at (pre-Faza 2) sau dupa un backfill masiv.

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


def _ts_uri_atinse_de_inserari(senzor_id: int,
                               de_la_created: Optional[datetime]) -> Optional[list[datetime]]:
    """ts-urile citirilor INSERATE dupa watermark (created_at > de_la_created).

    Returneaza None daca de_la_created e None (= rebuild complet: tot istoricul).
    Altfel lista de timestamp-uri (ts, timpul masurarii) ale citirilor noi -
    folosita ca sa aflam exact ce bucket-uri trebuie recalculate. O citire late
    (ts vechi, created_at recent) apare aici pentru ca filtram pe created_at.
    Citirile cu created_at NULL (randuri pre-Faza 2) NU apar -> nu reproceseaza
    spurios la fiecare rulare; pentru ele se foloseste --full.
    """
    if de_la_created is None:
        return None
    randuri = (db.session.query(SensorReading.ts)
               .filter(SensorReading.senzor_id == senzor_id,
                       SensorReading.created_at.isnot(None),
                       SensorReading.created_at > de_la_created)
               .all())
    return [r[0] for r in randuri]


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


def _recalc_bucket_din_raw(senzor_id: int, bucket: str, bucket_ts: datetime) -> Optional[dict]:
    """Recalculeaza min/max/avg/count ale UNUI bucket din TOATE citirile lui.

    Citire marginita la [bucket_ts, bucket_ts + 1 bucket) -> un singur bucket, nu
    tot istoricul (nu reintroduce OOM-ul). Returneaza None daca bucket-ul nu mai
    are nicio citire (ex. toate purjate de retention dupa ce a fost atins).
    """
    pas = timedelta(hours=1) if bucket == '1h' else timedelta(days=1)
    citiri = (db.session.query(SensorReading.valoare)
              .filter(SensorReading.senzor_id == senzor_id,
                      SensorReading.ts >= bucket_ts,
                      SensorReading.ts < bucket_ts + pas)
              .all())
    if not citiri:
        return None
    v_min = float('inf'); v_max = float('-inf'); v_sum = 0.0; v_count = 0
    for (val,) in citiri:
        v = float(val)
        if v < v_min:
            v_min = v
        if v > v_max:
            v_max = v
        v_sum += v
        v_count += 1
    return {'min': v_min, 'max': v_max, 'avg': v_sum / v_count, 'count': v_count}


def rollup_senzor(senzor: Senzor, *,
                  buckets: tuple[str, ...] = ('1h', '1d'),
                  full: bool = False,
                  commit: bool = True,
                  **_kw) -> dict:
    """
    Materializeaza (incremental) rollup-ul unui senzor pentru bucket-urile date.

    Watermark pe INSERARE (Senzor.last_rollup_at), nu pe timpul masurarii:
      1. de_la = None daca full=True sau senzorul nu a fost rollup-at inca
         (last_rollup_at NULL) -> reprocesam tot istoricul. Altfel de_la =
         last_rollup_at.
      2. Aflam bucket-urile atinse de citiri INSERATE dupa de_la (created_at >
         de_la). O citire late (ts vechi, created_at recent) intra aici, deci
         bucket-ul ei vechi e reprocesat -> echivalenta rollup==Python pastrata.
      3. Pentru fiecare bucket atins recalculam din TOATE citirile lui (recompute
         complet) si facem UPSERT pe (senzor, bucket, bucket_ts) (idempotent).
      4. Salvam last_rollup_at = momentul de start al rularii.

    `lookback_buckets` (kwarg vechi) e acceptat dar IGNORAT (compatibilitate
    inapoi) - watermark-ul pe created_at nu mai are nevoie de suprapunere.

    Returneaza {'buckets_create': N, 'buckets_update': M, 'citiri_procesate': K}.
    """
    rezultat = {'buckets_create': 0, 'buckets_update': 0, 'citiri_procesate': 0}

    for bucket in buckets:
        if bucket not in _BUCKET_FMT:
            raise ValueError(f'bucket invalid: {bucket} (folositi 1h sau 1d)')

    # Momentul de start = noul watermark. Il citim INAINTE de a procesa, ca orice
    # citire inserata in timpul rularii (created_at >= run_at) sa fie prinsa la
    # rularea urmatoare (nu pierduta intre citire si salvarea watermark-ului).
    run_at = datetime.utcnow()
    de_la = None if full else senzor.last_rollup_at

    # ts-urile citirilor noi (sau toate, daca de_la None) -> bucket-urile de
    # recalculat. Le aflam o singura data (acelasi set pentru toate bucket-urile).
    ts_uri = _ts_uri_atinse_de_inserari(senzor.id, de_la)
    if ts_uri is None:
        # Rebuild complet: toate bucket-urile cu cel putin o citire.
        ts_uri = [r[0] for r in
                  db.session.query(SensorReading.ts)
                  .filter(SensorReading.senzor_id == senzor.id).all()]

    for bucket in buckets:
        # Set de chei bucket_ts (deduplicat) pentru granularitatea curenta.
        chei = {_bucket_ts(t, bucket) for t in ts_uri}
        if not chei:
            continue

        for key in chei:
            agg = _recalc_bucket_din_raw(senzor.id, bucket, key)
            if agg is None:
                continue
            creat = _upsert_bucket(
                senzor, bucket, key,
                v_min=agg['min'], v_max=agg['max'],
                v_avg=agg['avg'], v_count=agg['count'],
            )
            if creat:
                rezultat['buckets_create'] += 1
            else:
                rezultat['buckets_update'] += 1
            rezultat['citiri_procesate'] += agg['count']

    # Avansam watermark-ul indiferent daca am avut bucket-uri noi (idempotent:
    # urmatoarea rulare fara citiri noi nu mai gaseste nimic de reprocesat).
    senzor.last_rollup_at = run_at

    if commit:
        db.session.commit()
    return rezultat


def rollup_all(*, buckets: tuple[str, ...] = ('1h', '1d'),
               full: bool = False,
               doar_activi: bool = True,
               commit: bool = True,
               **_kw) -> dict:
    """
    Ruleaza rollup-ul incremental pentru toti senzorii (activi).

    Apelat de CLI 'flask iot-rollup'. Commit o singura data la final (un write
    pe SQLite). Idempotent: a 2-a rulare fara citiri noi nu schimba nimic.
    full=True -> rebuild complet (ignora watermark-ul per senzor).
    `lookback_buckets` acceptat dar ignorat (compatibilitate inapoi).
    """
    q = Senzor.query
    if doar_activi:
        q = q.filter(Senzor.activ.is_(True))
    senzori = q.all()

    total = {'senzori': 0, 'buckets_create': 0, 'buckets_update': 0,
             'citiri_procesate': 0}
    for s in senzori:
        r = rollup_senzor(s, buckets=buckets, full=full, commit=False)
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
