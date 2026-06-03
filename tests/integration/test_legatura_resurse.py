"""Test conexiunea reala F3 <-> C pe cod de resursa (reconciliere + timp + drill-down)."""
from datetime import date

# F3 deviz cu extrase: capitol + sub-articole cu cod de resursa in denumire
F3 = (
    "Nr;Capitol de lucrari;U.M.;Cantitatea;;Pretul unitar;TOTALUL\n"
    "0;1;2;3;;4;5\n"
    "1;CAP - Capitol fatada;mp;100;;200;20000\n"
    ";;;material:;;150;15000\n"
    ";;;manopera:;;50;5000\n"
    "1.1;111 - Vata material;mp;100;;150;15000\n"
    "1.2;222 - Zugrav munca;ora;200;;30;6000\n"
).encode("utf-8")


def _setup(app):
    from models import db, Proiect, GanttPlan, ExtrasResursa
    with app.app_context():
        p = Proiect(cod_proiect='LEG-1', nume='Leg', data_start=date(2026, 1, 5))
        db.session.add(p); db.session.flush()
        db.session.add(GanttPlan(nume='F3', continut=F3, ext='.csv', proiect_id=p.id,
                                 data_start=date(2026, 1, 5), nr_activitati=0,
                                 durata_zile=0, cost_total=0))
        db.session.add(ExtrasResursa(proiect_id=p.id, tip='material', cod='111',
                                     denumire='Vata', um='mp', cantitate=100,
                                     tarif_unitar=150, valoare=15000))
        db.session.add(ExtrasResursa(proiect_id=p.id, tip='manopera', cod='222',
                                     denumire='Zugrav', um='ora', cantitate=200,
                                     tarif_unitar=30, valoare=6000))
        db.session.commit()
        return p.id


def _cleanup(app, pid):
    from models import db, Proiect, GanttPlan, ExtrasResursa
    with app.app_context():
        ExtrasResursa.query.filter_by(proiect_id=pid).delete()
        for x in GanttPlan.query.filter_by(proiect_id=pid).all():
            db.session.delete(x)
        pr = db.session.get(Proiect, pid)
        if pr:
            db.session.delete(pr)
        db.session.commit()


def test_legatura_pe_cod(app):
    from services.deviz_extras import legatura_resurse
    pid = _setup(app)
    try:
        with app.app_context():
            leg = legatura_resurse(pid)
        assert leg['are_plan'] and leg['are_extrase']
        byc = {r['cod']: r for r in leg['resurse']}
        # reconciliere la nivel de articol: F3 = C => ok
        assert byc['111']['f3_cant'] == 100 and byc['111']['extras_cant'] == 100
        assert byc['111']['status'] == 'ok'
        # drill-down (activitati) + necesar in timp (luni)
        assert byc['111']['activitati'] and byc['111']['luni']
        # tip preluat din extras
        assert byc['222']['tip'] == 'manopera'
    finally:
        _cleanup(app, pid)


def test_ruta_conexiune(authenticated_client, app):
    pid = _setup(app)
    try:
        r = authenticated_client.get(f'/proiecte/{pid}/resurse/conexiune')
        assert r.status_code == 200
        assert b'Conexiune F3' in r.data and b'111' in r.data and b'Vata' in r.data
    finally:
        _cleanup(app, pid)
