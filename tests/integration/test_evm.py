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
        # BAC = costul recalculat (cu preturi reale daca exista), > 0
        assert data is not None and data['bac'] > 0
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


def test_evm_manopera_pontata(authenticated_client, app):
    from models import db, Proiect, GanttPlan, Angajat, Pontaj
    from services.evm import evm_proiect
    with app.app_context():
        p = Proiect(cod_proiect='EVM-M', nume='M', data_start=date.today())
        a = Angajat(nume='Ion', prenume='Pop', data_angajare=date.today())
        db.session.add_all([p, a]); db.session.flush()
        db.session.add(GanttPlan(nume='Pl', continut=SAMPLE, ext='.csv', nr_activitati=2,
                                 durata_zile=10, cost_total=10000, proiect_id=p.id))
        db.session.add(Pontaj(angajat_id=a.id, proiect_id=p.id, data=date.today(), ore_lucrate=8))
        db.session.commit()
        pid, aid = p.id, a.id
        data = evm_proiect(pid)
        # 8 ore x 30 lei (tarif orar implicit) = 240
        assert abs(data['manopera']['cost'] - 240) < 1 and data['manopera']['ore'] == 8.0
    try:
        r = authenticated_client.get(f'/proiecte/{pid}/evm')
        assert r.status_code == 200 and b'Manopera pontata' in r.data
    finally:
        with app.app_context():
            for M in (Pontaj, GanttPlan):
                for x in M.query.filter_by(proiect_id=pid).all():
                    db.session.delete(x)
            a = db.session.get(Angajat, aid)
            if a:
                db.session.delete(a)
            pr = db.session.get(Proiect, pid)
            if pr:
                db.session.delete(pr)
            db.session.commit()


def test_risc_proiect_si_alerta(app, admin_user):
    from models import (db, Proiect, Contract, GanttPlan, SituatieLunara,
                        NotificareApp, Utilizator)
    from services.evm import risc_proiect
    from services.notificari_job import alerteaza_evm_risc
    with app.app_context():
        mid = Utilizator.query.filter_by(email='admin_test@test.local').first().id
        p = Proiect(cod_proiect='R-T', nume='R', data_start=date(2026, 1, 1),
                    status='activ', manager_id=mid)
        db.session.add(p); db.session.flush()
        c = Contract(proiect_id=p.id, nr_contract='C', data_semnare=date(2026, 1, 1))
        db.session.add(c); db.session.flush()
        db.session.add(GanttPlan(nume='Pl', continut=SAMPLE, ext='.csv', nr_activitati=2,
                                 durata_zile=100, cost_total=10000, proiect_id=p.id,
                                 data_start=date(2026, 1, 1)))
        db.session.add(SituatieLunara(proiect_id=p.id, contract_id=c.id, an=2026, luna=2,
                                      data_emitere=date(2026, 2, 28), procent_avans_total=50,
                                      valoare_cumulat_la_zi=6000))   # CPI = 5000/6000 = 0.83
        db.session.commit()
        pid = p.id
        r = risc_proiect(pid)
        assert r and r['cpi'] is not None and r['cpi'] < 0.9 and r['status'] == 'critic'
        NotificareApp.query.filter_by(utilizator_id=mid).delete(); db.session.commit()
        assert alerteaza_evm_risc() >= 1
        assert NotificareApp.query.filter_by(utilizator_id=mid, tip='evm_risc').count() >= 1
    with app.app_context():
        NotificareApp.query.filter_by(utilizator_id=mid).delete()
        for M in (SituatieLunara, GanttPlan, Contract):
            for x in M.query.filter_by(proiect_id=pid).all():
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
