"""Teste pentru EVM (plan Gantt vs situatii) la nivel de proiect."""
from datetime import date

SAMPLE = (
    b"cod_articol;denumire;um;cantitate;obiect;tronson;categorie\n"
    b"A1;Sapatura mecanizata;mc;100;O;T;Terasamente\n"
    b"A2;Pozare conducta PEHD;m;200;O;T;Conducte\n"
)


def test_evm_serviciu_si_ruta(authenticated_client, app):
    from models import db, Proiect, GanttPlan
    from services.evm import evm_proiect
    with app.app_context():
        p = Proiect(cod_proiect='EVM-T', nume='EVM test', data_start=date.today())
        db.session.add(p); db.session.flush()
        plan = GanttPlan(nume='Plan EVM', continut=SAMPLE, ext='.csv', nr_activitati=2,
                         durata_zile=10, cost_total=50000, proiect_id=p.id)
        db.session.add(plan); db.session.commit()
        pid = p.id
        data = evm_proiect(pid)
        assert data is not None and data['bac'] == 50000
        assert data['pv_curba']          # curba planificata (PV) exista
        assert data['serie'] == []       # fara situatii -> fara actuals
    try:
        r = authenticated_client.get(f'/proiecte/{pid}/evm')
        assert r.status_code == 200 and b'Earned Value' in r.data
    finally:
        with app.app_context():
            for x in GanttPlan.query.filter_by(proiect_id=pid).all():
                db.session.delete(x)
            pr = db.session.get(Proiect, pid)
            if pr:
                db.session.delete(pr)
            db.session.commit()


def test_evm_fara_plan(authenticated_client, app):
    from models import db, Proiect
    with app.app_context():
        p = Proiect(cod_proiect='EVM-T2', nume='Fara plan', data_start=date.today())
        db.session.add(p); db.session.commit()
        pid = p.id
    try:
        r = authenticated_client.get(f'/proiecte/{pid}/evm')
        assert r.status_code == 200 and b'Nu exista un plan' in r.data
    finally:
        with app.app_context():
            pr = db.session.get(Proiect, pid)
            if pr:
                db.session.delete(pr)
                db.session.commit()
