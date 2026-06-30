"""Teste pentru services/project_service.py (S1.3A — read/list + date financiare).

Serviciul este read-only si HTTP-free. Verificam tenant-scoping, filtre, sortare,
paginare, statistici, lista de manageri si formulele financiare, plus guard-uri
de boundary (fara mutatii, fara query brut, fara importuri HTTP).
"""

from datetime import date

import pytest
from flask import g


@pytest.fixture(autouse=True)
def curata_s13a(app):
    _curata(app)
    yield
    _curata(app)


# ============================================================
# Lista / context (read-only, tenant-safe)
# ============================================================

def test_list_context_doar_tenant_curent(app):
    from services.project_service import get_project_list_context
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            ctx = get_project_list_context()
        coduri = {p.cod_proiect for p in ctx['proiecte']}
        assert 'S13A-PA1' in coduri
        assert 'S13A-PB1' not in coduri  # proiect tenant strain nu apare


def test_list_context_filtru_status(app):
    from services.project_service import get_project_list_context
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            ctx = get_project_list_context(status_filtru='planificat')
        coduri = {p.cod_proiect for p in ctx['proiecte']}
        assert coduri == {'S13A-PA2'}


def test_list_context_filtru_cautare_nume_cod_beneficiar(app):
    from services.project_service import get_project_list_context
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            dupa_nume = {p.cod_proiect for p in get_project_list_context(cautare='Alpha')['proiecte']}
            dupa_cod = {p.cod_proiect for p in get_project_list_context(cautare='S13A-PA2')['proiecte']}
            dupa_benef = {p.cod_proiect for p in get_project_list_context(cautare='BeneUnu')['proiecte']}
        assert dupa_nume == {'S13A-PA1'}
        assert dupa_cod == {'S13A-PA2'}
        assert dupa_benef == {'S13A-PA1'}


def test_list_context_filtru_manager(app):
    from services.project_service import get_project_list_context
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            ctx = get_project_list_context(manager_filtru=str(ids['manager_a']))
        coduri = {p.cod_proiect for p in ctx['proiecte']}
        assert coduri == {'S13A-PA1'}


def test_list_context_sortare(app):
    from services.project_service import get_project_list_context
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            nume_asc = [p.nume for p in get_project_list_context(sort='nume_asc')['proiecte']]
            nume_desc = [p.nume for p in get_project_list_context(sort='nume_desc')['proiecte']]
        assert nume_asc == sorted(nume_asc)
        assert nume_desc == sorted(nume_desc, reverse=True)


def test_list_context_paginare_per_page_12(app):
    from services.project_service import get_project_list_context
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            ctx = get_project_list_context()
        assert ctx['pagination'].per_page == 12


def test_list_context_statistici(app):
    from services.project_service import get_project_list_context
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            ctx = get_project_list_context()
        assert ctx['total_active'] == 1
        assert ctx['total_planificate'] == 1
        assert ctx['total_finalizate'] == 1
        assert ctx['total_suspendate'] == 1


def test_list_context_buget_total_activ_planificat(app):
    from services.project_service import get_project_list_context
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            ctx = get_project_list_context()
        # 1000 (activ) + 500 (planificat); finalizat/suspendat excluse; tenant B exclus
        assert float(ctx['buget_total_all']) == 1500.0


def test_managers_tenant_safe(app):
    from services.project_service import get_project_managers
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            manageri = get_project_managers()
        mgr_ids = {m.id for m in manageri}
        assert ids['manager_a'] in mgr_ids
        assert ids['manager_b'] not in mgr_ids  # manager tenant strain nu apare


def test_list_context_view_mode_si_defaults(app):
    from services.project_service import get_project_list_context
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        with app.test_request_context('/'):
            ctx = get_project_list_context()
        assert ctx['view_mode'] == 'cards'
        assert ctx['sort'] == 'data_start_desc'
        ctx2 = None
        with app.test_request_context('/'):
            ctx2 = get_project_list_context(view_mode='list')
        assert ctx2['view_mode'] == 'list'


def test_list_context_shape_chei(app):
    from services.project_service import get_project_list_context
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            ctx = get_project_list_context()
        for cheie in ('proiecte', 'pagination', 'status_filtru', 'cautare',
                      'manager_filtru', 'sort', 'view_mode', 'total_active',
                      'total_planificate', 'total_finalizate', 'total_suspendate',
                      'buget_total_all', 'manageri'):
            assert cheie in ctx


# ============================================================
# Date financiare (read-only, tenant-safe)
# ============================================================

def test_total_ore_tenant_scoped(app):
    from services.project_service import get_project_total_hours
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            total = get_project_total_hours(ids['proiect_a'])
        assert total == 11.0


def test_total_ore_proiect_strain_fail_closed(app):
    from services.project_service import get_project_total_hours
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_b']
            # proiect_a apartine tenantului A; din tenant B -> fail closed -> 0
            total = get_project_total_hours(ids['proiect_a'])
        assert total == 0


def test_cost_manopera_formula(app):
    from services.project_service import calculate_project_labor_cost
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            cost = calculate_project_labor_cost(ids['proiect_a'])
        # 8*50 + 2*50*1.5 + 1*50*2 = 400 + 150 + 100 = 650
        assert cost == 650.0


def test_ore_saptamanale_shape_si_fereastra(app):
    from services.project_service import get_project_weekly_hours
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            saptamani = get_project_weekly_hours(ids['proiect_a'])
        assert len(saptamani) == 12
        for s in saptamani:
            assert set(s.keys()) == {'label', 'start', 'end', 'ore'}
        # pontajul de azi cade in ultima fereastra saptamanala
        assert saptamani[-1]['ore'] == 11.0


def test_cost_lunar_shape_si_fereastra(app):
    from services.project_service import get_project_monthly_costs
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            luni = get_project_monthly_costs(ids['proiect_a'])
        assert len(luni) == 6
        for l in luni:
            assert set(l.keys()) == {'label', 'cost'}
        # luna curenta: 11 ore * 50 tarif = 550
        assert luni[-1]['cost'] == 550.0


def test_financial_helpers_nu_muteaza(app):
    from models import Pontaj
    from services.project_service import (
        get_project_total_hours, calculate_project_labor_cost,
        get_project_weekly_hours, get_project_monthly_costs,
    )
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        inainte = Pontaj.query.count()
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            get_project_total_hours(ids['proiect_a'])
            calculate_project_labor_cost(ids['proiect_a'])
            get_project_weekly_hours(ids['proiect_a'])
            get_project_monthly_costs(ids['proiect_a'])
        assert Pontaj.query.count() == inainte  # niciun rand nou/sters


# ============================================================
# Guard-uri de boundary
# ============================================================

def test_service_http_free_si_read_only(app):
    """Guard: project_service nu importa Flask response API si nu muteaza."""
    import inspect
    import services.project_service as svc

    sursa = inspect.getsource(svc)
    # HTTP-free
    for token in ('flash(', 'redirect(', 'render_template(', 'jsonify(',
                  'send_file(', 'url_for(', 'request.'):
        assert token not in sursa, token
    # read-only
    assert 'db.session.add' not in sursa
    assert 'db.session.delete' not in sursa
    assert 'db.session.commit' not in sursa
    assert 'db.session.rollback' not in sursa


def test_service_fara_query_brut_tenant_owned(app):
    """Guard: fara query brut tenant-owned; foloseste helperii tenant-safe."""
    import inspect
    import services.project_service as svc

    sursa = inspect.getsource(svc)
    assert 'Proiect.query' not in sursa
    assert 'Pontaj.query' not in sursa
    assert 'Angajat.query' not in sursa
    assert 'RaportActivitate.query' not in sursa
    assert 'query_for_tenant' in sursa
    assert 'query_timesheets_for_tenant' in sursa
    assert 'query_project_assignments_for_tenant' in sursa


# ============================================================
# Fixture data
# ============================================================

def _seed(app):
    from models import Angajat, AngajatProiect, Pontaj, Proiect, Tenant, Utilizator, db
    with app.app_context():
        ta = Tenant(cod='test-s13a-a', nume='Tenant S13A A')
        tb = Tenant(cod='test-s13a-b', nume='Tenant S13A B')
        db.session.add_all([ta, tb])
        db.session.commit()

        mgr_a = Utilizator(tenant_id=ta.id, nume='S13A-Mgr', prenume='A',
                           email='s13a-mgr-a@test.local', parola_hash='x',
                           rol='manager', activ=True)
        mgr_b = Utilizator(tenant_id=tb.id, nume='S13A-Mgr', prenume='B',
                           email='s13a-mgr-b@test.local', parola_hash='x',
                           rol='manager', activ=True)
        db.session.add_all([mgr_a, mgr_b])
        db.session.commit()

        p_a1 = Proiect(tenant_id=ta.id, cod_proiect='S13A-PA1', nume='S13A Alpha',
                       beneficiar='BeneUnu', data_start=date(2026, 1, 1),
                       status='activ', buget_total=1000, manager_id=mgr_a.id)
        p_a2 = Proiect(tenant_id=ta.id, cod_proiect='S13A-PA2', nume='S13A Beta',
                       beneficiar='BeneDoi', data_start=date(2026, 2, 1),
                       status='planificat', buget_total=500)
        p_a3 = Proiect(tenant_id=ta.id, cod_proiect='S13A-PA3', nume='S13A Gamma',
                       data_start=date(2026, 3, 1), status='finalizat', buget_total=300)
        p_a4 = Proiect(tenant_id=ta.id, cod_proiect='S13A-PA4', nume='S13A Delta',
                       data_start=date(2026, 4, 1), status='suspendat', buget_total=200)
        p_b1 = Proiect(tenant_id=tb.id, cod_proiect='S13A-PB1', nume='S13A Strain',
                       data_start=date(2026, 1, 1), status='activ', buget_total=9999)
        db.session.add_all([p_a1, p_a2, p_a3, p_a4, p_b1])
        db.session.commit()

        ang_a = Angajat(tenant_id=ta.id, nume='S13A-Ang', prenume='A', cnp='1950101010101',
                        functie='Muncitor', data_angajare=date(2026, 1, 1), status='activ')
        db.session.add(ang_a)
        db.session.commit()

        db.session.add(AngajatProiect(angajat_id=ang_a.id, proiect_id=p_a1.id,
                                      tarif_negociat=50))
        db.session.add(Pontaj(angajat_id=ang_a.id, proiect_id=p_a1.id, data=date.today(),
                              ore_lucrate=11, ore_normale=8, ore_suplimentare_50=2,
                              ore_suplimentare_100=1, status='draft', observatii='TEST_S13A'))
        db.session.commit()

        return {
            'tenant_a': ta.id, 'tenant_b': tb.id,
            'manager_a': mgr_a.id, 'manager_b': mgr_b.id,
            'proiect_a': p_a1.id, 'angajat_a': ang_a.id,
        }


def _curata(app):
    from models import Angajat, AngajatProiect, Pontaj, Proiect, Tenant, Utilizator, db
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        prj_ids = [p.id for p in Proiect.query.filter(
            Proiect.cod_proiect.like('S13A-%')).all()]
        ang_ids = [a.id for a in Angajat.query.filter(Angajat.nume.like('S13A-%')).all()]
        if prj_ids:
            for p in Pontaj.query.filter(Pontaj.proiect_id.in_(prj_ids)).all():
                db.session.delete(p)
            for ap in AngajatProiect.query.filter(
                AngajatProiect.proiect_id.in_(prj_ids)).all():
                db.session.delete(ap)
        for proiect in Proiect.query.filter(Proiect.cod_proiect.like('S13A-%')).all():
            db.session.delete(proiect)
        for ang in Angajat.query.filter(Angajat.nume.like('S13A-%')).all():
            db.session.delete(ang)
        for u in Utilizator.query.filter(Utilizator.email.like('s13a-%')).all():
            db.session.delete(u)
        for tenant in Tenant.query.filter(Tenant.cod.like('test-s13a-%')).all():
            db.session.delete(tenant)
        db.session.commit()
