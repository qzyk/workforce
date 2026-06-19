"""
Teste de integrare pentru urmarirea executiei Gantt (Faza 2 tracking):
- gating pe flag-ul 'gantt-tracking' (OFF -> 404 + comportament istoric: progres 0)
- inghetare baseline + comparatie curent vs baseline
- progres bulk append-only (form + JSON)
- adaptor DB (tracking_db) cu flag ON/OFF
"""
import io

import pytest

from services.gantt.normalizare import cheie_stabila

# cheia stabila a primei activitati (ART001) - calculata direct din componente,
# identica cu ce produce pipeline-ul (cheie_stabila in pipeline.clasifica_articole).
CHEIE_ART001 = cheie_stabila('ART001', 'Sapatura mecanizata', 'Retea', 'Strada A')

SAMPLE = (
    b"cod_articol;denumire;um;cantitate;obiect;tronson;categorie\n"
    b"ART001;Sapatura mecanizata;mc;100;Retea;Strada A;Terasamente\n"
    b"ART002;Pozare conducta PEHD;m;200;Retea;Strada A;Conducte\n"
)


@pytest.fixture(autouse=True)
def _curata(app):
    yield
    from models import (db, GanttPlan, GanttBaseline, GanttProgres)
    from services.feature_flags import FeatureFlag
    with app.app_context():
        try:
            for m in (GanttProgres, GanttBaseline, GanttPlan):
                for row in m.query.all():
                    db.session.delete(row)
            for ff in FeatureFlag.query.filter_by(key='gantt-tracking').all():
                db.session.delete(ff)
            db.session.commit()
        except Exception:
            db.session.rollback()


def _salveaza_plan(client, app, nume='Plan tr'):
    client.post('/gantt/genereaza',
                data={'fisier': (io.BytesIO(SAMPLE), 'plan.csv')},
                content_type='multipart/form-data')
    client.post('/gantt/salveaza', data={'nume': nume})
    from models import GanttPlan
    with app.app_context():
        return GanttPlan.query.filter_by(nume=nume).first().id


def _activeaza_tracking(app):
    from services.feature_flags import set_flag
    with app.app_context():
        set_flag('gantt-tracking', True)


# ------------------------------------------------------------- gating flag OFF
def test_tracking_404_cu_flag_off(authenticated_client, app):
    pid = _salveaza_plan(authenticated_client, app)
    # flag OFF (default) -> toate rutele de tracking dau 404
    assert authenticated_client.get(f'/gantt/plan/{pid}/tracking').status_code == 404
    assert authenticated_client.post(f'/gantt/plan/{pid}/baseline').status_code == 404
    assert authenticated_client.post(f'/gantt/plan/{pid}/progres').status_code == 404


def test_plan_progres_zero_cu_flag_off(authenticated_client, app):
    """Regresie: cu flag OFF, diagrama planului are bare cu progres 0 (istoric)."""
    pid = _salveaza_plan(authenticated_client, app)
    r = authenticated_client.get(f'/gantt/plan/{pid}')
    assert r.status_code == 200
    # diagrama trimite progress: 0 si baseline gol (nu se afiseaza link de tracking)
    assert b'"progress": 0' in r.data or b'"progress":0' in r.data
    assert b'Urmarire executie' not in r.data


# ------------------------------------------------------------- flag ON
def test_baseline_freeze_si_compara(authenticated_client, app):
    pid = _salveaza_plan(authenticated_client, app)
    _activeaza_tracking(app)

    # pagina de tracking se deschide
    assert authenticated_client.get(f'/gantt/plan/{pid}/tracking').status_code == 200

    # inghet baseline
    r = authenticated_client.post(f'/gantt/plan/{pid}/baseline', data={'nume': 'BL1'})
    assert r.status_code == 302

    from models import db, GanttBaseline, GanttPlan
    with app.app_context():
        bl = GanttBaseline.query.filter_by(plan_id=pid).first()
        assert bl is not None and bl.nume == 'BL1'
        p = db.session.get(GanttPlan, pid)
        assert p.baseline_activ_id == bl.id   # marcat ca activ
        bid = bl.id

    # comparatia curent vs baseline (identic) -> 200, zero chei disparute/noi
    rc = authenticated_client.get(f'/gantt/plan/{pid}/baseline/{bid}')
    assert rc.status_code == 200
    assert b'Curent vs baseline' in rc.data


def test_progres_bulk_form_append_only(authenticated_client, app):
    pid = _salveaza_plan(authenticated_client, app)
    _activeaza_tracking(app)

    from models import GanttProgres
    from services.gantt import tracking_db
    cheie = CHEIE_ART001

    # POST form bulk: pct_<cheie>=50
    r = authenticated_client.post(f'/gantt/plan/{pid}/progres',
                                  data={f'pct_{cheie}': '50'})
    assert r.status_code == 302

    with app.app_context():
        rows = GanttProgres.query.filter_by(plan_id=pid).all()
        assert len(rows) == 1 and float(rows[0].procent_fizic) == 50.0
        # append-only: a doua salvare adauga un rand nou (nu actualizeaza)
    authenticated_client.post(f'/gantt/plan/{pid}/progres', data={f'pct_{cheie}': '80'})
    with app.app_context():
        rows = GanttProgres.query.filter_by(plan_id=pid).all()
        assert len(rows) == 2
        curent = tracking_db.progrese_active(pid)   # flag ON -> dict
        assert curent[cheie] == 80.0                # progres curent = ultima masuratoare


def test_progres_bulk_json(authenticated_client, app):
    pid = _salveaza_plan(authenticated_client, app)
    _activeaza_tracking(app)

    r = authenticated_client.post(
        f'/gantt/plan/{pid}/progres',
        json={'progrese': [{'cheie': CHEIE_ART001, 'procent': 30}]})
    assert r.status_code == 200 and r.get_json()['adaugate'] == 1


def test_tracking_db_flag_gating(app):
    """progrese_active / baseline_activ intorc None cu flag OFF (zero regresie)."""
    from services.gantt import tracking_db
    with app.app_context():
        assert tracking_db.progrese_active(123) is None
        class _P:  # plan fals fara baseline
            baseline_activ_id = None
        assert tracking_db.baseline_activ(_P()) is None
