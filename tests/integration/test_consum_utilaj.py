"""Teste Faza 3 (C): ConsumUtilaj - utilaj real pe proiect + EVM planificat vs real."""
from datetime import date


def _cleanup(app, pid=None):
    from models import db, Proiect, GanttPlan, ConsumUtilaj
    with app.app_context():
        if pid:
            for M in (ConsumUtilaj, GanttPlan):
                for x in M.query.filter_by(proiect_id=pid).all():
                    db.session.delete(x)
            p = db.session.get(Proiect, pid)
            if p:
                db.session.delete(p)
        db.session.commit()


def test_calc_cost_model(app):
    """cost explicit are prioritate; altfel ore x tarif_ora."""
    from models import ConsumUtilaj
    with app.app_context():
        assert ConsumUtilaj(denumire='X', ore=8, tarif_ora=120, cost=0).calc_cost() == 960.0
        assert ConsumUtilaj(denumire='X', ore=8, tarif_ora=120, cost=1000).calc_cost() == 1000.0


def test_evm_utilaj_real(app):
    """evm_proiect intoarce utilaj.real = suma consumului inregistrat + serie."""
    from models import db, Proiect, GanttPlan, ConsumUtilaj
    from services.evm import evm_proiect
    SAMPLE = (b"cod_articol;denumire;um;cantitate;obiect;tronson\n"
              b"TS01;Sapatura mecanizata;mc;100;O;T\n")
    with app.app_context():
        p = Proiect(cod_proiect='UT-1', nume='Utilaj', data_start=date.today())
        db.session.add(p); db.session.flush()
        db.session.add(GanttPlan(nume='Pl', continut=SAMPLE, ext='.csv', nr_activitati=1,
                                 durata_zile=10, cost_total=10000, proiect_id=p.id,
                                 data_start=date.today()))
        db.session.add_all([
            ConsumUtilaj(proiect_id=p.id, denumire='Excavator', data=date.today(),
                         ore=8, tarif_ora=120, cost=0),       # 960
            ConsumUtilaj(proiect_id=p.id, denumire='Macara', data=date.today(),
                         ore=0, tarif_ora=0, cost=500),        # 500 explicit
        ])
        db.session.commit()
        pid = p.id
        ev = evm_proiect(pid)
        assert ev is not None and 'utilaj' in ev
        assert ev['utilaj']['real'] == 1460.0          # 960 + 500
        assert ev['utilaj']['ore'] == 8.0
        assert ev['utilaj']['planificat'] >= 0
    _cleanup(app, pid)


def test_ruta_utilaje_crud(authenticated_client, app):
    """GET pagina; POST adauga (cost = ore x tarif); POST sterge."""
    from models import db, Proiect, ConsumUtilaj
    with app.app_context():
        p = Proiect(cod_proiect='UT-2', nume='Utilaj2', data_start=date.today())
        db.session.add(p); db.session.commit()
        pid = p.id
    try:
        r = authenticated_client.get(f'/proiecte/{pid}/utilaje')
        assert r.status_code == 200 and b'Utilaje' in r.data

        authenticated_client.post(f'/proiecte/{pid}/utilaje/adauga', data={
            'denumire': 'Buldozer', 'ore': '10', 'tarif_ora': '150', 'data': date.today().isoformat(),
        }, follow_redirects=True)
        with app.app_context():
            row = ConsumUtilaj.query.filter_by(proiect_id=pid, denumire='Buldozer').first()
            assert row is not None and float(row.cost) == 1500.0   # 10 x 150
            cid = row.id

        authenticated_client.post(f'/proiecte/{pid}/utilaje/{cid}/sterge', follow_redirects=True)
        with app.app_context():
            assert db.session.get(ConsumUtilaj, cid) is None
    finally:
        _cleanup(app, pid)
