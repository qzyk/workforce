"""Test puntea BIM <-> F3 <-> C: QTO model pe categorie + reconciliere + resurse."""
from datetime import date


def _cleanup(app, pid):
    from models import (db, Proiect, GanttPlan, ProiectSantier, ElementBIM,
                        Cladire, Santier)
    with app.app_context():
        ProiectSantier.query.filter_by(proiect_id=pid).delete()
        for x in GanttPlan.query.filter_by(proiect_id=pid).all():
            db.session.delete(x)
        for cl in Cladire.query.filter_by(cod='BIMD-C1').all():
            ElementBIM.query.filter_by(cladire_id=cl.id).delete()
            db.session.delete(cl)
        for s in Santier.query.filter_by(cod='BIMD-S1').all():
            db.session.delete(s)
        pr = db.session.get(Proiect, pid)
        if pr:
            db.session.delete(pr)
        db.session.commit()


def test_legatura_bim(app):
    from models import (db, Proiect, Santier, Cladire, ElementBIM, ProiectSantier,
                        GanttPlan)
    from services.legatura_bim import legatura_bim, TIP_F2
    csv = b"cod_articol;denumire;um;cantitate;pret unitar\nA1;Montaj armatura;kg;200;5\n"
    with app.app_context():
        p = Proiect(cod_proiect='BIMD-1', nume='x', data_start=date.today())
        db.session.add(p); db.session.flush()
        s = Santier(cod='BIMD-S1', nume='S'); db.session.add(s); db.session.flush()
        cl = Cladire(santier_id=s.id, cod='BIMD-C1', nume='C'); db.session.add(cl); db.session.flush()
        db.session.add(ProiectSantier(proiect_id=p.id, santier_id=s.id))
        for i in range(2):
            db.session.add(ElementBIM(cod=f'R{i}', tip_element='rebar', cladire_id=cl.id,
                                      cantitate=100, unitate_masura='kg', ifc_global_id=f'GBD{i}'))
        db.session.add(GanttPlan(nume='F3', continut=csv, ext='.csv', proiect_id=p.id,
                                 data_start=date.today(), nr_activitati=1, durata_zile=5,
                                 cost_total=1000))
        db.session.commit(); pid = p.id
        leg = legatura_bim(pid)
        assert leg['are_model'] is True and leg['are_plan'] is True
        assert leg['nr_elemente'] == 2
        byc = {c['categorie']: c for c in leg['categorii']}
        # rebar -> armatura (determinist) cu cantitatea din model
        assert TIP_F2['rebar'] == 'armatura'
        assert 'armatura' in byc and byc['armatura']['model_cant'] == 200
        # structura completa pe fiecare rand
        c = byc['armatura']
        assert {'categorie', 'model_cant', 'model_um', 'f3_cant', 'status',
                'resurse'} <= set(c)
        assert c['status'] in ('ok', 'atentie', 'critic', 'info', 'doar_model', 'doar_deviz')
    _cleanup(app, pid)


def test_ruta_bim_deviz(authenticated_client, app):
    from models import db, Proiect
    with app.app_context():
        p = Proiect(cod_proiect='BIMD-2', nume='x', data_start=date.today())
        db.session.add(p); db.session.commit(); pid = p.id
    try:
        r = authenticated_client.get(f'/proiecte/{pid}/bim-deviz')
        assert r.status_code == 200 and b'BIM' in r.data
    finally:
        with app.app_context():
            pr = db.session.get(Proiect, pid)
            if pr:
                db.session.delete(pr); db.session.commit()
