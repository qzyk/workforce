"""Teste Editor WBS: seed din auto, reconstructie din arbore, operatii editor."""
from datetime import date

SAMPLE = (b"cod_articol;denumire;um;cantitate;obiect;tronson\n"
          b"TS01;Sapatura mecanizata;mc;100;Obiect A;Tronson 1\n"
          b"AR01;Montaj armatura BST500;kg;200;Obiect A;Tronson 1\n")


def _setup(app):
    from models import db, Proiect, GanttPlan
    from services.gantt.pipeline import MotorPlanificare
    from services.gantt import wbs_editor
    with app.app_context():
        p = Proiect(cod_proiect='WBS-T', nume='WBS', data_start=date.today())
        db.session.add(p); db.session.flush()
        plan = GanttPlan(nume='Pl', continut=SAMPLE, ext='.csv', nr_activitati=2,
                         durata_zile=5, cost_total=0, proiect_id=p.id, data_start=date.today())
        db.session.add(plan); db.session.commit()
        rez, _ = MotorPlanificare().genereaza_din_fisier(SAMPLE, '.csv')
        n = wbs_editor.seed_arbore(plan, rez.noduri_wbs)
        return plan.id, p.id, n


def _cleanup(app, plan_id, pid):
    from models import db, Proiect, GanttPlan, GanttWbsNod
    with app.app_context():
        GanttWbsNod.query.filter_by(plan_id=plan_id).delete()
        gp = db.session.get(GanttPlan, plan_id)
        if gp:
            db.session.delete(gp)
        pr = db.session.get(Proiect, pid)
        if pr:
            db.session.delete(pr)
        db.session.commit()


def test_seed_din_auto(app):
    from models import GanttWbsNod
    plan_id, pid, n = _setup(app)
    try:
        with app.app_context():
            noduri = GanttWbsNod.query.filter_by(plan_id=plan_id).all()
            assert len(noduri) == n and n > 0
            frunze = [x for x in noduri if x.tip == 'activitate']
            assert len(frunze) == 2                      # TS01 + AR01
            assert all(f.activitate_ref and f.activitate_ref.startswith('A') for f in frunze)
            assert any(x.tip == 'grup' for x in noduri)   # exista grupuri (obiect/tronson/categ)
    finally:
        _cleanup(app, plan_id, pid)


def test_wbs_din_arbore_roundtrip(app):
    from services.gantt.pipeline import MotorPlanificare
    from services.gantt import wbs_editor
    plan_id, pid, _ = _setup(app)
    try:
        with app.app_context():
            rez, _ = MotorPlanificare().genereaza_din_fisier(SAMPLE, '.csv')
            noduri_db = wbs_editor.noduri_plan(plan_id)
            out = wbs_editor.wbs_din_arbore(rez.activitati, noduri_db)
            assert out and all(getattr(a, 'wbs_id', '') for a in rez.activitati)
            frunze = [x for x in out if x.tip == 'activitate']
            assert len(frunze) == 2
    finally:
        _cleanup(app, plan_id, pid)


def test_wbs_din_arbore_orfane(app):
    """O activitate care nu e in arbore ajunge in grupul 'Neincadrate'."""
    from services.gantt.pipeline import MotorPlanificare
    from services.gantt import wbs_editor
    from services.gantt.modele import Activitate
    plan_id, pid, _ = _setup(app)
    try:
        with app.app_context():
            rez, _ = MotorPlanificare().genereaza_din_fisier(SAMPLE, '.csv')
            extra = Activitate(id='A999999', cod='Z9', nume='Activitate noua',
                               categorie_tehnologica=None, obiect='X', tronson='Y',
                               um='buc', cantitate=1, durata=1)
            noduri_db = wbs_editor.noduri_plan(plan_id)
            out = wbs_editor.wbs_din_arbore(rez.activitati + [extra], noduri_db)
            assert any(x.nume == 'Neincadrate' for x in out)
            assert extra.wbs_id   # a primit pozitie
    finally:
        _cleanup(app, plan_id, pid)


def test_ruta_editor_si_integrare(authenticated_client, app):
    """GET editor seedeaza + 200; redenumire; planul randat foloseste arborele editat."""
    from models import db, Proiect, GanttPlan, GanttWbsNod
    with app.app_context():
        p = Proiect(cod_proiect='WBS-R', nume='WBSr', data_start=date.today())
        db.session.add(p); db.session.flush()
        plan = GanttPlan(nume='PlanR', continut=SAMPLE, ext='.csv', nr_activitati=2,
                         durata_zile=5, cost_total=0, proiect_id=p.id, data_start=date.today())
        db.session.add(plan); db.session.commit()
        plan_id, pid = plan.id, p.id
    try:
        r = authenticated_client.get(f'/gantt/plan/{plan_id}/wbs')
        assert r.status_code == 200 and b'Editor WBS' in r.data
        with app.app_context():
            gid = GanttWbsNod.query.filter_by(plan_id=plan_id, tip='grup').first().id
        authenticated_client.post(f'/gantt/plan/{plan_id}/wbs/op', data={
            'actiune': 'redenumeste', 'nod_id': gid, 'nume': 'GRUP EDITAT XYZ'},
            follow_redirects=True)
        with app.app_context():
            assert db.session.get(GanttWbsNod, gid).nume == 'GRUP EDITAT XYZ'
        r2 = authenticated_client.get(f'/gantt/plan/{plan_id}')           # randare cu arbore editat
        assert r2.status_code == 200 and b'GRUP EDITAT XYZ' in r2.data
    finally:
        _cleanup(app, plan_id, pid)


def test_salveaza_si_editeaza_wbs(authenticated_client, app):
    """Din previzualizare: 'Salveaza si editeaza WBS' -> plan + arbore seedat + redirect editor."""
    from io import BytesIO
    from models import db, GanttPlan, GanttWbsNod
    authenticated_client.post('/gantt/genereaza',
                              data={'fisier': (BytesIO(SAMPLE), 'f.csv')},
                              content_type='multipart/form-data', follow_redirects=True)
    with authenticated_client.session_transaction() as sess:
        token = sess.get('gantt_token')
    assert token
    r = authenticated_client.post('/gantt/salveaza', data={
        'token': token, 'nume': 'Plan WBS direct', 'actiune': 'wbs'})
    assert r.status_code in (302, 303) and '/wbs' in r.headers.get('Location', '')
    with app.app_context():
        plan = GanttPlan.query.filter_by(nume='Plan WBS direct').first()
        assert plan is not None and GanttWbsNod.query.filter_by(plan_id=plan.id).count() > 0
        plan_id = plan.id
    with app.app_context():
        GanttWbsNod.query.filter_by(plan_id=plan_id).delete()
        gp = db.session.get(GanttPlan, plan_id)
        if gp:
            db.session.delete(gp)
        db.session.commit()


def test_operatii_editor(app):
    from models import GanttWbsNod
    from services.gantt import wbs_editor
    plan_id, pid, _ = _setup(app)
    try:
        with app.app_context():
            # adauga grup + redenumeste
            g = wbs_editor.adauga_grup(type('P', (), {'id': plan_id, 'tenant_id': None})(),
                                       'Grup nou')
            assert g and wbs_editor.redenumeste(plan_id, g.id, 'Grup redenumit')
            assert GanttWbsNod.query.get(g.id).nume == 'Grup redenumit'
            # muta o frunza in grupul nou
            frunza = GanttWbsNod.query.filter_by(plan_id=plan_id, tip='activitate').first()
            assert wbs_editor.muta_in_grup(plan_id, frunza.id, g.id)
            assert GanttWbsNod.query.get(frunza.id).parinte_id == g.id
            # reset -> arborele dispare
            assert wbs_editor.reset(plan_id) > 0
            assert not wbs_editor.arbore_exista(plan_id)
    finally:
        _cleanup(app, plan_id, pid)
