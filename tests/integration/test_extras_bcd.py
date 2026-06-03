"""Teste B (C8->utilaj planificat EVM), C (aprovizionare CSV), D (reconciliere F3<->extrase)."""
from datetime import date


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


def test_b_evm_utilaj_din_c8(app):
    from models import db, Proiect, GanttPlan, ExtrasResursa
    from services.evm import evm_proiect
    sample = b"cod_articol;denumire;um;cantitate;obiect;tronson\nT;Test;mc;10;O;T\n"
    with app.app_context():
        p = Proiect(cod_proiect='BCD-1', nume='x', data_start=date.today())
        db.session.add(p); db.session.flush()
        db.session.add(GanttPlan(nume='Pl', continut=sample, ext='.csv', nr_activitati=1,
                                 durata_zile=10, cost_total=1000, proiect_id=p.id,
                                 data_start=date.today()))
        db.session.add(ExtrasResursa(proiect_id=p.id, tip='utilaj', denumire='Macara',
                                     cantitate=18, tarif_unitar=28, valoare=504))
        db.session.commit(); pid = p.id
        ev = evm_proiect(pid)
        assert ev['utilaj']['sursa'] == 'C8'
        assert ev['utilaj']['planificat'] == 504 and ev['utilaj']['planificat_ore'] == 18
    _cleanup(app, pid)


def test_c_aprovizionare_csv(authenticated_client, app):
    from models import db, Proiect, ExtrasResursa
    with app.app_context():
        p = Proiect(cod_proiect='BCD-2', nume='x', data_start=date.today())
        db.session.add(p); db.session.flush()
        db.session.add(ExtrasResursa(proiect_id=p.id, tip='material', cod='M1', denumire='Vata',
                                     um='mp', cantitate=100, tarif_unitar=78, valoare=7800,
                                     furnizor='Depozit'))
        db.session.commit(); pid = p.id
    try:
        r = authenticated_client.get(f'/proiecte/{pid}/resurse/aprovizionare.csv')
        assert r.status_code == 200
        assert b'Furnizor' in r.data and b'Vata' in r.data and b'Depozit' in r.data
    finally:
        _cleanup(app, pid)


def test_d_reconciliere(app):
    from models import db, Proiect, GanttPlan, ExtrasResursa
    from services.deviz_extras import reconciliere
    csv = (b"cod_articol;denumire;um;cantitate;pret unitar;pret material;pret manopera\n"
           b"A;X;mc;10;100;60;40\n")
    with app.app_context():
        p = Proiect(cod_proiect='BCD-3', nume='x', data_start=date.today())
        db.session.add(p); db.session.flush()
        db.session.add(GanttPlan(nume='Pl', continut=csv, ext='.csv', nr_activitati=1,
                                 durata_zile=5, cost_total=1000, proiect_id=p.id,
                                 data_start=date.today()))
        db.session.add(ExtrasResursa(proiect_id=p.id, tip='material', denumire='m',
                                     cantitate=1, tarif_unitar=600, valoare=600))
        db.session.add(ExtrasResursa(proiect_id=p.id, tip='manopera', denumire='om',
                                     cantitate=1, tarif_unitar=400, valoare=400))
        db.session.commit(); pid = p.id
        rec = reconciliere(pid)
        assert rec['are_plan'] and rec['are_extrase']
        assert rec['material']['f3'] == 600 and rec['material']['extras'] == 600
        assert rec['material']['status'] == 'ok' and rec['manopera']['status'] == 'ok'
        assert rec['utilaj']['status'] == 'lipsa'      # fara extras utilaj
    _cleanup(app, pid)
