"""Faza 3 auto-planning: norme + generare program executie din elemente BIM."""
from datetime import date
from decimal import Decimal


def _user(app):
    from models import db, Utilizator
    u = Utilizator.query.filter_by(email='plan@test.local').first()
    if not u:
        u = Utilizator(nume='P', prenume='L', email='plan@test.local', rol='admin', activ=True)
        u.set_password('x'); db.session.add(u); db.session.commit()
    return u


def _santier_cu_elemente(app):
    from models import db, Santier, Cladire, Nivel, ElementBIM
    s = Santier(cod='PRJ-PL', nume='Plan'); db.session.add(s); db.session.flush()
    c = Cladire(santier_id=s.id, cod='C', nume='C'); db.session.add(c); db.session.flush()
    n = Nivel(cladire_id=c.id, cod='P', nume='Parter', ordine=0); db.session.add(n); db.session.flush()
    db.session.add_all([
        ElementBIM(cladire_id=c.id, nivel_id=n.id, cod='B', tip_element='beam',
                   material='Beton C25/30', cantitate=Decimal('100'), unitate_masura='mc'),
        ElementBIM(cladire_id=c.id, nivel_id=n.id, cod='W', tip_element='wall',
                   material='caramida', cantitate=Decimal('200'), unitate_masura='mp'),
    ])
    db.session.commit()
    return s.id


class TestPlanificare:
    def test_seed_norme_idempotent(self, app):
        from services import planificare_bim
        with app.app_context():
            assert planificare_bim.seed_norme(tenant_id=None) > 0
            assert planificare_bim.seed_norme(tenant_id=None) == 0

    def test_genereaza_program_ordine_si_zile(self, app):
        from models import ElementBIM, BIMTaskSchedule
        from services import planificare_bim
        with app.app_context():
            u = _user(app)
            sid = _santier_cu_elemente(app)
            res = planificare_bim.genereaza_program(sid, date(2026, 6, 1), u)
            assert res['status'] == 'ok'
            assert res['nr_taskuri'] == 2
            beam = ElementBIM.query.filter_by(cod='B').first()
            wall = ElementBIM.query.filter_by(cod='W').first()
            sb = BIMTaskSchedule.query.filter_by(element_bim_id=beam.id).first()
            sw = BIMTaskSchedule.query.filter_by(element_bim_id=wall.id).first()
            # beton (faza structura) inainte de zidarie
            assert sw.data_start_plan >= sb.data_sfarsit_plan
            # start pe zi lucratoare (nu weekend)
            assert sb.data_start_plan.weekday() < 5
            # durata beton: 100 mc / 25 mc/zi = 4 zile lucratoare
            assert (sb.data_sfarsit_plan - sb.data_start_plan).days >= 3

    def test_idempotent_rerun(self, app):
        from models import BIMTaskSchedule, ElementBIM
        from services import planificare_bim
        with app.app_context():
            u = _user(app)
            sid = _santier_cu_elemente(app)
            planificare_bim.genereaza_program(sid, date(2026, 6, 1), u)
            planificare_bim.genereaza_program(sid, date(2026, 6, 1), u)
            beam = ElementBIM.query.filter_by(cod='B').first()
            n = BIMTaskSchedule.query.filter_by(element_bim_id=beam.id,
                                                descriere='auto-planning').count()
            assert n == 1


class TestPlanificareRoute:
    def test_flag_off_redirect(self, app, authenticated_client):
        from models import db, Santier
        from services.feature_flags import set_flag
        with app.app_context():
            s = Santier(cod='PRJ-PLR', nume='R'); db.session.add(s); db.session.commit()
            sid = s.id
            set_flag('bim-auto-planning', False, commit=True)
        r = authenticated_client.post(f'/bim/santier/{sid}/genereaza-program',
                                      data={'data_start': '2026-06-01'}, follow_redirects=False)
        assert r.status_code in (302, 303)
