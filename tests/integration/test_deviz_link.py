"""Teste pentru 5D real: cost Gantt din pozitiile BoQ pretuite (deviz)."""
from datetime import date

from services.gantt.modele import ArticolF3
from services.gantt.cost import calculeaza_cost
from services.gantt.normalizare import normalizeaza_cheie


def test_cost_din_boq_pret_real():
    art = ArticolF3('ART001', 'Sapatura', um='mc', cantitate=10)
    pb = {'cod': {normalizeaza_cheie('ART001'): {'pu': 150, 'mat': 90, 'man': 60}}, 'den': {}}
    val, mat, man, uti, est = calculeaza_cost(art, 'SAPATURA', {'SAPATURA': {'tarif': 35}}, pb)
    assert val == 1500.0 and est is False        # pret real din deviz -> nu e estimat
    assert mat == 900.0 and man == 600.0 and uti == 0.0


def test_cost_din_boq_cu_utilaj():
    art = ArticolF3('ART003', 'Sapatura mecanizata', um='mc', cantitate=10)
    pb = {'cod': {normalizeaza_cheie('ART003'):
                  {'pu': 150, 'mat': 30, 'man': 40, 'uti': 80}}, 'den': {}}
    val, mat, man, uti, est = calculeaza_cost(art, 'SAPATURA', {}, pb)
    assert val == 1500.0 and est is False
    assert mat == 300.0 and man == 400.0 and uti == 800.0   # utilajul iese separat


def test_pipeline_propaga_utilaj_din_deviz(app):
    """Utilajul din deviz se propaga prin pipeline -> activitate + statistici."""
    from services.gantt import import_engine
    from services.gantt.pipeline import MotorPlanificare
    pb = {'cod': {normalizeaza_cheie('ART9'):
                  {'pu': 100, 'mat': 20, 'man': 30, 'uti': 50}}, 'den': {}}
    csv = (b"cod_articol;denumire;um;cantitate;obiect;tronson\n"
           b"ART9;Excavare mecanizata;mc;10;O;T\n")
    with app.app_context():
        art, _ = import_engine.importa(csv, '.csv')
        rez = MotorPlanificare(preturi_boq=pb).proceseaza(art)
    a = rez.activitati[0]
    assert a.valoare == 1000.0 and a.valoare_utilaj == 500.0
    assert rez.statistici['cost_utilaj'] == 500.0


def test_pret_utilaj_din_coloana_f3(app):
    """Coloana 'pret utilaj' din F3 -> Activitate.valoare_utilaj (cale reala cu setari)."""
    from services.gantt.pipeline import MotorPlanificare
    csv = (b"cod_articol;denumire;um;cantitate;pret unitar;pret material;pret manopera;pret utilaj\n"
           b"A;Lucrare;mc;10;10;5;3;2\n")
    with app.app_context():
        rez, _ = MotorPlanificare().genereaza_din_fisier(csv, '.csv', clasifica=False)
    a = rez.activitati[0]
    assert a.valoare == 100.0 and a.valoare_utilaj == 20.0   # 10 x 2


def test_preturi_proiect_si_motor(app):
    from models import db, Proiect, Contract, OfertaContract, PozitieBoQ
    from services.deviz_link import preturi_proiect, are_preturi
    from services.gantt import import_engine
    from services.gantt.pipeline import MotorPlanificare
    with app.app_context():
        p = Proiect(cod_proiect='5D-T', nume='5D', data_start=date.today())
        db.session.add(p); db.session.flush()
        c = Contract(proiect_id=p.id, nr_contract='C1', data_semnare=date.today())
        db.session.add(c); db.session.flush()
        of = OfertaContract(contract_id=c.id, proiect_id=p.id, data_emitere=date.today())
        db.session.add(of); db.session.flush()
        db.session.add(PozitieBoQ(oferta_id=of.id, proiect_id=p.id, cod_articol='ART002',
                                  denumire='Pozare conducta', um='m', pret_unitar=120,
                                  valoare_materiale_unitar=80, valoare_manopera_unitar=40))
        db.session.commit()
        pid = p.id
        pb = preturi_proiect(pid)
        assert are_preturi(pb)

        csv = (b"cod_articol;denumire;um;cantitate;obiect;tronson;categorie\n"
               b"ART002;Pozare conducta;m;100;O;T;Conducte\n")
        art, _ = import_engine.importa(csv, '.csv')
        rez = MotorPlanificare(preturi_boq=pb).proceseaza(art)
        a = rez.activitati[0]
        assert a.valoare == 12000.0 and a.cost_estimat is False   # 100 x 120, real
    try:
        pass
    finally:
        with app.app_context():
            for M in (PozitieBoQ, OfertaContract, Contract):
                for x in M.query.filter_by(proiect_id=pid).all():
                    db.session.delete(x)
            pr = db.session.get(Proiect, pid)
            if pr:
                db.session.delete(pr)
            db.session.commit()
