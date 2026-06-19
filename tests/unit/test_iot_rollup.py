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


# ====================================================
# Echivalenta get_history: rollup == agregare Python
# ====================================================

def test_get_history_din_rollup_egal_cu_python(app, element, admin, flag_rollup_on):
    """
    Cu flag ON si fereastra >= 24h, get_history din rollup == agregarea Python
    pe aceleasi citiri. Fereastra > 24h => ramura rollup.
    """
    with app.app_context():
        s = _senzor(element, admin, 'R-EQ')
        # Citiri pe 3 zile, mai multe ore/zi
        base = datetime(2026, 5, 1, 0, 0)
        valori = []
        for zi in range(3):
            for ora in (2, 8, 14, 20):
                off = zi * 24 * 60 + ora * 60
                # valori variate ca min/max/avg sa fie semnificative
                valori.append((off, 10 + zi * 5 + ora))
        _seed_citiri(s, base, valori)

        from_ts = base - timedelta(hours=1)
        to_ts = base + timedelta(days=3)

        # Referinta: agregarea Python directa pe citirile raw.
        ref_1h = iot_query._history_din_readings(s.id, from_ts, to_ts, '1h')
        ref_1d = iot_query._history_din_readings(s.id, from_ts, to_ts, '1d')

        # Materializam rollup-ul.
        iot_rollup.rollup_senzor(s)

        # Cu flag ON + fereastra >= 24h => get_history citeste din rollup.
        out_1h = iot_query.get_history(s.id, from_ts=from_ts, to_ts=to_ts, agg='1h')
        out_1d = iot_query.get_history(s.id, from_ts=from_ts, to_ts=to_ts, agg='1d')

        # Confirmam ca a folosit rollup-ul (nu Python) - sursa identica ca valori
        assert out_1h['data'] == ref_1h
        assert out_1d['data'] == ref_1d
        assert out_1h['count'] == len(ref_1h)
        assert out_1d['count'] == len(ref_1d)


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
