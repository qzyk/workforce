"""
Teste pentru IoT Faza 2: retention + rollup time-series.

Acopera:
- rollup incremental idempotent: a 2-a rulare nu dubleaza randuri (indexul unic
  (senzor_id, bucket, bucket_ts)) si recalculeaza aceleasi valori;
- echivalenta: get_history din rollup (flag 'iot-rollup' ON) da exact aceleasi
  bucket-uri/valori ca agregarea Python pe citirile raw;
- regresie flag OFF: get_history ramane pe agregarea Python (comportament
  istoric), chiar daca exista rollup materializat;
- fereastra < 24h: cu flag ON ramane pe Python (bucket-ul curent inca deschis);
- retention: cleanup_readings sterge citirile raw vechi, rollup-ul ramane.
"""

from datetime import datetime, timedelta
import pytest

from models import (db, Senzor, SensorReading, SensorRollup, ElementBIM,
                    Cladire, Santier, Utilizator)
from services import iot_ingest, iot_query, iot_rollup
from services import feature_flags as ff


# ====================================================
# Fixtures
# ====================================================

@pytest.fixture
def admin(app):
    with app.app_context():
        u = Utilizator.query.filter_by(email='iotr_admin@test.local').first()
        if not u:
            u = Utilizator(nume='IoTR', prenume='X', email='iotr_admin@test.local',
                           rol='admin', activ=True)
            u.set_password('x'); db.session.add(u); db.session.commit()
        return u.id


@pytest.fixture
def element(app):
    with app.app_context():
        s = Santier(cod='S-ROLL', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        el = ElementBIM(cladire_id=c.id, cod='E1', tip_element='wall',
                        status='construit', nume='W')
        db.session.add(el); db.session.commit()
        yield el.id


@pytest.fixture
def flag_rollup_on(app):
    """Activeaza flag-ul iot-rollup global; reset la final."""
    with app.app_context():
        ff.set_flag('iot-rollup', True)
    yield
    with app.app_context():
        ff.set_flag('iot-rollup', False)


def _senzor(element_id, admin_id, cod, **kw):
    u = Utilizator.query.get(admin_id)
    return iot_ingest.create_senzor(cod=cod, nume='X', tip='temperatura',
                                    element_bim_id=element_id, user=u, **kw)


def _seed_citiri(senzor, base, valori_la_minute):
    """Insereaza citiri: lista de (offset_minute, valoare)."""
    for off_min, val in valori_la_minute:
        iot_ingest.ingest_reading(senzor, val, ts=base + timedelta(minutes=off_min))


# ====================================================
# Rollup incremental + idempotenta
# ====================================================

def test_rollup_materializeaza_buckets(app, element, admin):
    with app.app_context():
        s = _senzor(element, admin, 'R-1')
        base = datetime(2026, 5, 10, 12, 0)
        # 3 citiri in ora 12, 1 in ora 13
        _seed_citiri(s, base, [(0, 10), (20, 20), (45, 30), (75, 50)])

        stats = iot_rollup.rollup_senzor(s)
        # 2 bucket-uri orare create + 1 bucket zilnic
        rollups_1h = SensorRollup.query.filter_by(senzor_id=s.id, bucket='1h').all()
        rollups_1d = SensorRollup.query.filter_by(senzor_id=s.id, bucket='1d').all()
        assert len(rollups_1h) == 2
        assert len(rollups_1d) == 1

        # Ora 12: min=10, max=30, avg=20, count=3
        b12 = next(r for r in rollups_1h
                   if r.bucket_ts == datetime(2026, 5, 10, 12, 0))
        assert float(b12.v_min) == 10
        assert float(b12.v_max) == 30
        assert float(b12.v_avg) == 20.0
        assert b12.v_count == 3

        # Ziua: min=10, max=50, count=4
        bzi = rollups_1d[0]
        assert float(bzi.v_min) == 10
        assert float(bzi.v_max) == 50
        assert bzi.v_count == 4
        assert stats['citiri_procesate'] > 0


def test_rollup_a_doua_rulare_nu_dubleaza(app, element, admin):
    """Idempotenta: a 2-a rulare fara citiri noi nu adauga randuri."""
    with app.app_context():
        s = _senzor(element, admin, 'R-2')
        base = datetime(2026, 5, 11, 8, 0)
        _seed_citiri(s, base, [(0, 5), (30, 15)])

        iot_rollup.rollup_senzor(s)
        nr_dupa_prima = SensorRollup.query.filter_by(senzor_id=s.id).count()

        # A 2-a rulare - identic, fara citiri noi
        iot_rollup.rollup_senzor(s)
        nr_dupa_a_doua = SensorRollup.query.filter_by(senzor_id=s.id).count()

        assert nr_dupa_a_doua == nr_dupa_prima  # zero dubluri (index unic)

        # Valorile raman corecte (recalcul identic)
        b = SensorRollup.query.filter_by(
            senzor_id=s.id, bucket='1h',
            bucket_ts=datetime(2026, 5, 11, 8, 0)).one()
        assert float(b.v_min) == 5
        assert float(b.v_max) == 15
        assert b.v_count == 2


def test_rollup_incremental_actualizeaza_bucket_deschis(app, element, admin):
    """Citiri noi in acelasi bucket dupa un rollup -> bucket actualizat, fara dublu."""
    with app.app_context():
        s = _senzor(element, admin, 'R-3')
        base = datetime(2026, 5, 12, 9, 0)
        _seed_citiri(s, base, [(0, 10), (10, 20)])
        iot_rollup.rollup_senzor(s)

        b = SensorRollup.query.filter_by(
            senzor_id=s.id, bucket='1h', bucket_ts=base).one()
        assert b.v_count == 2
        assert float(b.v_max) == 20

        # O citire noua in acelasi bucket (ora 9)
        iot_ingest.ingest_reading(s, 40, ts=base + timedelta(minutes=40))
        iot_rollup.rollup_senzor(s)

        # Acelasi rand (UPSERT), count actualizat la 3, max la 40
        randuri = SensorRollup.query.filter_by(
            senzor_id=s.id, bucket='1h', bucket_ts=base).all()
        assert len(randuri) == 1
        assert randuri[0].v_count == 3
        assert float(randuri[0].v_max) == 40


def test_rollup_all_doar_activi(app, element, admin):
    with app.app_context():
        s = _senzor(element, admin, 'R-4')
        base = datetime(2026, 5, 13, 10, 0)
        _seed_citiri(s, base, [(0, 11), (5, 22)])
        stats = iot_rollup.rollup_all()
        assert stats['senzori'] >= 1
        assert SensorRollup.query.filter_by(senzor_id=s.id).count() >= 1


def test_rollup_citire_late_in_bucket_vechi_recuperata(app, element, admin):
    """
    MAJOR (review): o citire ingestata in dezordine (ts backdatat) intr-un bucket
    DEJA inchis, mai vechi decat orice fereastra de lookback, TREBUIE recuperata
    de re-rularea 'flask iot-rollup'. Watermark-ul pe created_at o prinde (ts vechi,
    created_at recent). Reproduce exact scenariul din review:
      3 zile orare -> rollup -> ingest 999 in day0 h05 -> 5x re-rollup ->
      bucketul 1h day0 h05 = count=2, max=999, avg=507 (nu count=1, max=15).
    """
    with app.app_context():
        s = _senzor(element, admin, 'R-LATE')
        day0 = datetime(2026, 3, 1, 0, 0)
        # 3 zile de citiri orare; ora h are valoarea 10 + (h % 24) la :30.
        for h in range(72):
            iot_ingest.ingest_reading(s, 10 + (h % 24),
                                      ts=day0 + timedelta(hours=h, minutes=30))
        iot_rollup.rollup_senzor(s)

        # Bucketul day0 h05 inainte de citirea late: count=1, max=15 (10+5).
        b05 = SensorRollup.query.filter_by(
            senzor_id=s.id, bucket='1h',
            bucket_ts=day0 + timedelta(hours=5)).one()
        assert b05.v_count == 1 and float(b05.v_max) == 15.0

        # Citire late in day0 h05 (bucket inchis, vechi de zile -> peste lookback).
        iot_ingest.ingest_reading(s, 999, ts=day0 + timedelta(hours=5, minutes=10))

        # Re-rulam de mai multe ori (idempotent): bucketul vechi e recalculat.
        for _ in range(5):
            iot_rollup.rollup_senzor(s)

        b05 = SensorRollup.query.filter_by(
            senzor_id=s.id, bucket='1h',
            bucket_ts=day0 + timedelta(hours=5)).one()
        assert b05.v_count == 2
        assert float(b05.v_max) == 999.0
        assert float(b05.v_avg) == 507.0   # (15 + 999) / 2

        # Echivalenta rollup==Python pe ramura rollup (fereastra > 24h) dupa fix.
        ff.set_flag('iot-rollup', True)
        try:
            from_ts = day0 - timedelta(hours=1)
            to_ts = day0 + timedelta(days=3)
            ref = iot_query._history_din_readings(s.id, from_ts, to_ts, '1h')
            out = iot_query.get_history(s.id, from_ts=from_ts, to_ts=to_ts,
                                        agg='1h')['data']
            assert out == ref
            d = {x['ts']: x for x in out}
            assert d['2026-03-01T05:00:00']['max'] == 999.0
            assert d['2026-03-01T05:00:00']['count'] == 2
        finally:
            ff.set_flag('iot-rollup', False)


def test_rollup_a_doua_rulare_fara_citiri_noi_nu_atinge_buckets(app, element, admin):
    """
    Watermark pe created_at: a 2-a rulare fara citiri INSERATE intre timp nu mai
    recalculeaza niciun bucket (zero create/update), dar avanseaza watermark-ul.
    """
    with app.app_context():
        s = _senzor(element, admin, 'R-WM')
        base = datetime(2026, 5, 20, 7, 0)
        _seed_citiri(s, base, [(0, 5), (30, 15), (70, 25)])
        r1 = iot_rollup.rollup_senzor(s)
        assert r1['buckets_create'] >= 1
        assert s.last_rollup_at is not None

        r2 = iot_rollup.rollup_senzor(s)
        # Nicio citire noua -> nimic de reprocesat.
        assert r2['buckets_create'] == 0
        assert r2['buckets_update'] == 0
        assert r2['citiri_procesate'] == 0


def test_rollup_full_reconstruieste_din_zero(app, element, admin):
    """
    Rebuild complet (full=True / 'flask iot-rollup --full'): ignora watermark-ul si
    reproceseaza tot istoricul. Util pentru randuri vechi fara created_at sau dupa
    un backfill masiv ingerat in dezordine.
    """
    with app.app_context():
        s = _senzor(element, admin, 'R-FULL')
        base = datetime(2026, 5, 21, 0, 0)
        _seed_citiri(s, base, [(30, 10), (90, 20), (24 * 60 + 30, 30)])
        iot_rollup.rollup_senzor(s)

        # Simulam randuri 'pre-Faza 2' (created_at NULL) inserate intr-un bucket
        # vechi: watermark-ul incremental nu le-ar prinde (filtreaza created_at NOT
        # NULL), dar --full le include.
        from models import db, SensorReading
        r = SensorReading(senzor_id=s.id, tenant_id=s.tenant_id,
                          ts=base + timedelta(minutes=45), valoare=500)
        db.session.add(r); db.session.flush()
        r.created_at = None
        db.session.commit()

        # Incremental NU prinde randul cu created_at NULL.
        iot_rollup.rollup_senzor(s)
        b0 = SensorRollup.query.filter_by(
            senzor_id=s.id, bucket='1h', bucket_ts=base).one()
        assert float(b0.v_max) == 10.0   # inca fara 500

        # Full DA: recalculeaza bucketul din toate citirile.
        iot_rollup.rollup_senzor(s, full=True)
        b0 = SensorRollup.query.filter_by(
            senzor_id=s.id, bucket='1h', bucket_ts=base).one()
        assert float(b0.v_max) == 500.0
        assert b0.v_count == 2


# ====================================================
# Echivalenta get_history: rollup == agregare Python
# ====================================================

def test_get_history_din_rollup_egal_cu_python(app, element, admin, flag_rollup_on):
    """
    Cu flag ON si fereastra >= 24h, get_history din rollup == agregarea Python
    pe aceleasi citiri. Fereastra > 24h => ramura rollup.

    IMPORTANT: ferestrele NU sunt aliniate la granitele de bucket - cad in
    MIJLOCUL bucket-urilor de margine (from la HH:20, to la HH:35), cu citiri de
    o parte si de alta a marginii. Asta exercita bucket-ul de inceput partial si
    bucket-ul de coada partial - exact unde ramura rollup diverge de Python daca
    filtreaza naiv pe bucket_ts. Versiunea anterioara a testului folosea doar
    margini aliniate (base-1h .. base+3 zile) si ascundea defectul.
    """
    with app.app_context():
        s = _senzor(element, admin, 'R-EQ')
        # Citiri pe 3 zile, mai multe ore/zi; ca marginile sa taie bucket-uri cu
        # citiri inauntru SI in afara ferestrei, punem cate 2 citiri/ora la :10 si :50.
        base = datetime(2026, 5, 1, 0, 0)
        valori = []
        for zi in range(3):
            for ora in (0, 2, 8, 14, 20, 23):
                off = zi * 24 * 60 + ora * 60
                valori.append((off + 10, 10 + zi * 5 + ora))   # citire la :10
                valori.append((off + 50, 30 + zi * 5 + ora))   # citire la :50
        _seed_citiri(s, base, valori)

        # Fereastra in mijloc de bucket: incepe la HH:20 (intre :10 si :50 ->
        # bucket de inceput partial, citirea :10 ramane afara, :50 inauntru) si
        # se termina tot la HH:35 in alt bucket (coada partiala: :10 inauntru,
        # :50 afara). Latime > 24h => ramura rollup.
        from_ts = base + timedelta(minutes=20)               # zi 0, ora 0, :20
        to_ts = base + timedelta(days=2, hours=14, minutes=35)  # zi 2, ora 14, :35

        # Referinta: agregarea Python directa pe citirile raw (clip la fereastra).
        ref_1h = iot_query._history_din_readings(s.id, from_ts, to_ts, '1h')
        ref_1d = iot_query._history_din_readings(s.id, from_ts, to_ts, '1d')

        # Sanity: referinta chiar contine bucket-uri de margine PARTIALE (altfel
        # testul nu ar exercita defectul). Bucketul de inceput 00:00 are doar
        # citirea :50 (count=1), nu ambele.
        b_start = next(b for b in ref_1h if b['ts'] == '2026-05-01T00:00:00')
        assert b_start['count'] == 1   # doar :50 prins, :10 e inainte de from_ts

        # Materializam rollup-ul (stocheaza bucket-ul 00:00 INTREG: count=2).
        iot_rollup.rollup_senzor(s)
        b_full = SensorRollup.query.filter_by(
            senzor_id=s.id, bucket='1h',
            bucket_ts=datetime(2026, 5, 1, 0, 0)).one()
        assert b_full.v_count == 2   # rollup are bucket-ul intreg, Python doar 1

        # Cu flag ON + fereastra >= 24h => get_history citeste din rollup, dar
        # reconciliaza marginile din raw -> identic cu Python pe ORICE fereastra.
        out_1h = iot_query.get_history(s.id, from_ts=from_ts, to_ts=to_ts, agg='1h')
        out_1d = iot_query.get_history(s.id, from_ts=from_ts, to_ts=to_ts, agg='1d')

        assert out_1h['data'] == ref_1h
        assert out_1d['data'] == ref_1d
        assert out_1h['count'] == len(ref_1h)
        assert out_1d['count'] == len(ref_1d)


def test_get_history_rollup_margini_partiale_explicit(app, element, admin, flag_rollup_on):
    """
    Reproduce exact cele doua divergente raportate la review (cu flag ON):
      (a) bucket de INCEPUT cu bucket_ts < from_ts dar cu citiri in fereastra:
          Python il pastreaza partial, ramura rollup naiva l-ar pierde;
      (b) bucket de COADA cu bucket_ts <= to_ts dar cu citiri DUPA to_ts:
          Python nu il are, ramura rollup naiva l-ar raporta intreg.
    Dupa fix, ambele ramuri dau identic; verificam si valorile concrete.
    """
    with app.app_context():
        s = _senzor(element, admin, 'R-MARG')
        base = datetime(2026, 6, 1, 5, 0)
        # ora 05: 4 citiri (:05,:10,:25,:40); ora 06: 1 citire la :05; +1 zi: ora
        # de coada cu o singura citire la :15.
        _seed_citiri(s, base, [
            (5, 100), (10, 110), (25, 120), (40, 130),
            (65, 200),
            (24 * 60 + 60 + 15, 900),   # zi+1, 06:15
        ])
        iot_rollup.rollup_senzor(s)

        # from la 05:20 (mijloc bucket 05:00): :05/:10 afara, :25/:40 inauntru
        from_ts = base + timedelta(minutes=20)
        # to la (zi+1) 06:05: citirea de la 06:15 e DUPA -> bucketul de coada
        # 06:00 NU trebuie sa apara.
        to_ts = base + timedelta(minutes=24 * 60 + 60 + 5)

        ref = iot_query._history_din_readings(s.id, from_ts, to_ts, '1h')
        out = iot_query.get_history(s.id, from_ts=from_ts, to_ts=to_ts, agg='1h')['data']

        assert out == ref

        d = {b['ts']: b for b in out}
        # (a) bucketul de inceput 05:00 exista, PARTIAL: doar :25 si :40
        assert d['2026-06-01T05:00:00']['count'] == 2
        assert d['2026-06-01T05:00:00']['min'] == 120.0
        assert d['2026-06-01T05:00:00']['max'] == 130.0
        # (b) bucketul de coada (06:00 din zi+1) NU apare (citirea :15 e dupa to_ts)
        assert '2026-06-02T06:00:00' not in d


def test_get_history_flag_on_rollup_gol_cade_pe_python(app, element, admin, flag_rollup_on):
    """
    MAJOR (review): flag ON + fereastra >= 24h + rollup GOL (cron neconfigurat /
    senzor proaspat backfilled) NU trebuie sa intoarca serie trunchiata/goala.
    Flag-ul si cron-ul sunt independente -> daca rollup-ul nu acopera fereastra,
    get_history cade pe agregarea Python (== _history_din_readings), nu pe rollup.
    Reproduce determinist: 5 zile de citiri, flag ON, ZERO randuri in rollup.
    """
    with app.app_context():
        s = _senzor(element, admin, 'R-EMPTY')
        base = datetime(2026, 7, 1, 0, 0)
        # 5 zile orare -> 120 bucket-uri 1h.
        for h in range(5 * 24):
            iot_ingest.ingest_reading(s, 20 + (h % 24), ts=base + timedelta(hours=h))

        # NU rulam rollup -> rollup gol.
        assert SensorRollup.query.filter_by(senzor_id=s.id).count() == 0

        from_ts = base
        to_ts = base + timedelta(days=5)   # fereastra 120h >= 24h -> ramura rollup
        ref = iot_query._history_din_readings(s.id, from_ts, to_ts, '1h')
        out = iot_query.get_history(s.id, from_ts=from_ts, to_ts=to_ts, agg='1h')

        # Cu rollup gol, ramura rollup ar fi intors ~0 bucket-uri interioare;
        # dupa fix cade pe Python -> identic, 120 bucket-uri.
        assert out['data'] == ref
        assert out['count'] == len(ref)
        assert out['count'] == 120


def test_get_history_flag_on_rollup_in_urma_cade_pe_python(app, element, admin, flag_rollup_on):
    """
    Flag ON + rollup IN URMA (materializat partial, lipsesc bucket-urile noi):
    get_history nu trebuie sa trunchieze coada. Cron-ul a rulat candva, apoi au mai
    sosit citiri dar n-a re-rulat -> bucket-urile interioare noi lipsesc din rollup
    -> cade pe Python (acoperire incompleta).
    """
    with app.app_context():
        s = _senzor(element, admin, 'R-BEHIND')
        base = datetime(2026, 8, 1, 0, 0)
        # Primele 3 zile, apoi rollup (cron 'la zi' la momentul ala).
        for h in range(3 * 24):
            iot_ingest.ingest_reading(s, 10 + (h % 24), ts=base + timedelta(hours=h))
        iot_rollup.rollup_senzor(s)
        rollup_dupa_3z = SensorRollup.query.filter_by(
            senzor_id=s.id, bucket='1h').count()

        # Inca 2 zile sosesc, dar cron-ul NU re-ruleaza -> rollup in urma.
        for h in range(3 * 24, 5 * 24):
            iot_ingest.ingest_reading(s, 10 + (h % 24), ts=base + timedelta(hours=h))

        from_ts = base
        to_ts = base + timedelta(days=5)
        ref = iot_query._history_din_readings(s.id, from_ts, to_ts, '1h')
        out = iot_query.get_history(s.id, from_ts=from_ts, to_ts=to_ts, agg='1h')

        # Fara fix, ramura rollup ar fi servit doar primele 3 zile (rollup_dupa_3z
        # bucket-uri) + margini -> coada zilelor 4-5 lipsea. Dupa fix == Python.
        assert out['data'] == ref
        assert out['count'] == 120
        assert rollup_dupa_3z < 120   # confirma ca rollup-ul chiar era in urma


def test_get_history_fereastra_mica_ramane_python(app, element, admin, flag_rollup_on):
    """Chiar cu flag ON, fereastra < 24h foloseste agregarea Python (bucket deschis)."""
    with app.app_context():
        s = _senzor(element, admin, 'R-SMALL')
        base = datetime.utcnow().replace(minute=0, second=0, microsecond=0) \
            - timedelta(hours=3)
        _seed_citiri(s, base, [(0, 10), (20, 20), (70, 30)])
        # NU rulam rollup -> daca ar citi din rollup ar fi gol; Python da date.
        out = iot_query.get_history(s.id, from_ts=base - timedelta(minutes=5),
                                    to_ts=datetime.utcnow(), agg='1h')
        assert out['count'] >= 1  # a folosit Python (rollup gol)
        total = sum(b['count'] for b in out['data'])
        assert total == 3


# ====================================================
# Regresie flag OFF
# ====================================================

def test_flag_off_foloseste_python_chiar_cu_rollup(app, element, admin):
    """
    Cu flag OFF, get_history ramane pe agregarea Python chiar daca exista rollup
    materializat (comportament istoric neschimbat).
    """
    with app.app_context():
        # asiguram flag OFF
        ff.set_flag('iot-rollup', False)
        s = _senzor(element, admin, 'R-OFF')
        base = datetime(2026, 4, 1, 0, 0)
        _seed_citiri(s, base, [(0, 100), (60, 200), (24 * 60, 300)])

        # Materializam rollup cu valori CORECTE
        iot_rollup.rollup_senzor(s)
        # Apoi corupem intentionat rollup-ul ca sa distingem sursa
        for r in SensorRollup.query.filter_by(senzor_id=s.id).all():
            r.v_min = -999; r.v_max = -999; r.v_avg = -999
        db.session.commit()

        from_ts = base - timedelta(hours=1)
        to_ts = base + timedelta(days=2)
        out = iot_query.get_history(s.id, from_ts=from_ts, to_ts=to_ts, agg='1h')

        # Daca ar fi citit din rollup, ar vedea -999. Python -> valori reale.
        assert all(b['min'] != -999 for b in out['data'])
        assert any(b['max'] == 200 for b in out['data'])


def test_history_agg_invalid_raises(app, element, admin):
    with app.app_context():
        s = _senzor(element, admin, 'R-INV')
        with pytest.raises(ValueError):
            iot_query.get_history(s.id, agg='saptamanal')


# ====================================================
# Retention
# ====================================================

def test_cleanup_readings_sterge_vechi_pastreaza_rollup(app, element, admin):
    with app.app_context():
        s = _senzor(element, admin, 'R-RET')
        acum = datetime.utcnow()
        # 2 citiri vechi (400 zile) + 1 recenta
        iot_ingest.ingest_reading(s, 10, ts=acum - timedelta(days=400))
        iot_ingest.ingest_reading(s, 20, ts=acum - timedelta(days=400, minutes=30))
        iot_ingest.ingest_reading(s, 30, ts=acum - timedelta(days=1))

        iot_rollup.rollup_senzor(s)
        rollup_inainte = SensorRollup.query.filter_by(senzor_id=s.id).count()
        assert rollup_inainte >= 1

        sterse = iot_rollup.cleanup_readings(older_than_days=365)
        assert sterse == 2  # cele 2 vechi

        ramase = SensorReading.query.filter_by(senzor_id=s.id).count()
        assert ramase == 1  # cea recenta

        # Rollup-ul NU e atins
        assert SensorRollup.query.filter_by(senzor_id=s.id).count() == rollup_inainte


def test_cleanup_readings_zero_dezactiveaza(app, element, admin):
    with app.app_context():
        s = _senzor(element, admin, 'R-RET0')
        iot_ingest.ingest_reading(s, 10, ts=datetime.utcnow() - timedelta(days=1000))
        sterse = iot_rollup.cleanup_readings(older_than_days=0)
        assert sterse == 0
        assert SensorReading.query.filter_by(senzor_id=s.id).count() == 1


def test_cleanup_events_deleaga_la_realtime(app):
    with app.app_context():
        from services import realtime as rt
        rt.publish_event('sensor_alert', payload={'x': 1})
        # eveniment proaspat -> nu se sterge cu 7 zile
        sterse = iot_rollup.cleanup_events(older_than_days=7)
        assert sterse == 0
