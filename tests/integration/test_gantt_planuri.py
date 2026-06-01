"""
Teste de integrare pentru planurile Gantt salvate (Faza 6):
salveaza -> listeaza -> deschide (re-ruleaza pipeline) -> export -> sterge.
"""
import io

import pytest

SAMPLE = (
    b"cod_articol;denumire;um;cantitate;obiect;tronson;categorie\n"
    b"ART001;Sapatura mecanizata;mc;100;Retea;Strada A;Terasamente\n"
    b"ART002;Pozare conducta PEHD;m;200;Retea;Strada A;Conducte\n"
)


@pytest.fixture(autouse=True)
def _curata_planuri(app):
    yield
    from models import db, GanttPlan
    with app.app_context():
        try:
            for p in GanttPlan.query.all():
                db.session.delete(p)
            db.session.commit()
        except Exception:
            db.session.rollback()


def _genereaza(client):
    return client.post('/gantt/genereaza',
                       data={'fisier': (io.BytesIO(SAMPLE), 'plan.csv')},
                       content_type='multipart/form-data')


def test_salveaza_listeaza_deschide(authenticated_client, app):
    assert _genereaza(authenticated_client).status_code == 200
    r = authenticated_client.post('/gantt/salveaza', data={'nume': 'Plan test'})
    assert r.status_code == 302 and '/gantt/plan/' in r.headers['Location']

    from models import GanttPlan
    with app.app_context():
        p = GanttPlan.query.filter_by(nume='Plan test').first()
        assert p is not None and p.nr_activitati > 0 and p.continut
        pid = p.id

    rl = authenticated_client.get('/gantt/planuri')
    assert rl.status_code == 200 and b'Plan test' in rl.data

    rd = authenticated_client.get(f'/gantt/plan/{pid}')          # re-ruleaza pipeline
    assert rd.status_code == 200 and b'Plan salvat' in rd.data


def test_export_din_plan(authenticated_client, app):
    _genereaza(authenticated_client)
    authenticated_client.post('/gantt/salveaza', data={'nume': 'P2'})
    from models import GanttPlan
    with app.app_context():
        pid = GanttPlan.query.filter_by(nume='P2').first().id
    r = authenticated_client.get(f'/gantt/plan/{pid}/export/csv')
    assert r.status_code == 200 and b'Activity Name' in r.data


def test_sterge_plan(authenticated_client, app):
    _genereaza(authenticated_client)
    authenticated_client.post('/gantt/salveaza', data={'nume': 'P3'})
    from models import db, GanttPlan
    with app.app_context():
        pid = GanttPlan.query.filter_by(nume='P3').first().id
    assert authenticated_client.post(f'/gantt/plan/{pid}/sterge').status_code == 302
    with app.app_context():
        assert db.session.get(GanttPlan, pid) is None


def test_plan_inexistent_404(authenticated_client):
    assert authenticated_client.get('/gantt/plan/999999').status_code == 404
