"""Teste pentru services/project_service.py (S1.3A — read/list + date financiare).

Serviciul este read-only si HTTP-free. Verificam tenant-scoping, filtre, sortare,
paginare, statistici, lista de manageri si formulele financiare, plus guard-uri
de boundary (fara mutatii, fara query brut, fara importuri HTTP).
"""

from datetime import date

import pytest
from flask import g
from werkzeug.exceptions import HTTPException


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
    """Guard: project_service nu apeleaza Flask response API; helperii read-only
    raman read-only (mutatiile sunt doar in salvarile S1.3B)."""
    import inspect
    import services.project_service as svc

    sursa = inspect.getsource(svc)
    # HTTP-free pe tot modulul
    for token in ('flash(', 'redirect(', 'render_template(', 'jsonify(',
                  'send_file(', 'url_for(', 'request.'):
        assert token not in sursa, token
    # read-only: helperii de citire/financiari nu fac mutatii/commit
    for fn_name in ('get_project_list_context', 'get_project_managers',
                    'get_project_total_hours', 'calculate_project_labor_cost',
                    'get_project_weekly_hours', 'get_project_monthly_costs'):
        s = inspect.getsource(getattr(svc, fn_name))
        assert 'db.session.add' not in s, fn_name
        assert 'db.session.delete' not in s, fn_name
        assert 'db.session.commit' not in s, fn_name
        assert 'db.session.rollback' not in s, fn_name
    # serviciul nu face niciodata rollback (conventia: ruta face rollback)
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
# S1.3B — salvari create/edit/status (mutante, tenant-safe)
# ============================================================

class _F:
    def __init__(self, data):
        self.data = data


def _proiect_form(*, cod_proiect='S13B-NEW', nume='S13B Nou', descriere=None,
                  judet=None, localitate=None, adresa_santier=None, beneficiar=None,
                  nr_contract_beneficiar=None, data_start=None,
                  data_sfarsit_planificat=None, data_sfarsit_real=None,
                  status='activ', manager_id=0, buget_total=None, buget_manopera=None):
    from types import SimpleNamespace
    return SimpleNamespace(
        cod_proiect=_F(cod_proiect), nume=_F(nume), descriere=_F(descriere),
        judet=_F(judet), localitate=_F(localitate), adresa_santier=_F(adresa_santier),
        beneficiar=_F(beneficiar), nr_contract_beneficiar=_F(nr_contract_beneficiar),
        data_start=_F(data_start or date(2026, 1, 1)),
        data_sfarsit_planificat=_F(data_sfarsit_planificat),
        data_sfarsit_real=_F(data_sfarsit_real),
        status=_F(status), manager_id=_F(manager_id),
        buget_total=_F(buget_total), buget_manopera=_F(buget_manopera),
    )


def test_create_asigneaza_tenant_id(app):
    from services.project_service import create_project_from_form_data
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            proiect = create_project_from_form_data(
                form_data=_proiect_form(cod_proiect='S13B-T1'))
            assert proiect.tenant_id == ids['tenant_a']


def test_create_mapare_campuri_si_defaults(app):
    from services.project_service import create_project_from_form_data
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        with app.test_request_context('/'):
            proiect = create_project_from_form_data(form_data=_proiect_form(
                cod_proiect='  S13B-T2  ', nume='  Nume  ', descriere=None,
                beneficiar=None, status='planificat', buget_total=1234))
            assert proiect.cod_proiect == 'S13B-T2'   # strip
            assert proiect.nume == 'Nume'             # strip
            assert proiect.descriere == ''            # None -> ''
            assert proiect.beneficiar == ''           # None -> ''
            assert proiect.status == 'planificat'
            assert proiect.manager_id is None          # manager_id 0 -> None
            assert float(proiect.buget_total) == 1234.0


def test_create_compune_locatie(app):
    from services.project_service import create_project_from_form_data
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        with app.test_request_context('/'):
            p1 = create_project_from_form_data(form_data=_proiect_form(
                cod_proiect='S13B-L1', judet='Cluj', localitate='Cluj-Napoca'))
            p2 = create_project_from_form_data(form_data=_proiect_form(
                cod_proiect='S13B-L2', judet='Cluj', localitate=None))
            p3 = create_project_from_form_data(form_data=_proiect_form(
                cod_proiect='S13B-L3', judet=None, localitate='OrasFaraJudet'))
            assert p1.locatie == 'Cluj-Napoca, Cluj'
            assert p2.locatie == 'Cluj'
            assert p3.locatie == ''   # fara judet -> gol (identic cu ruta)


def test_create_valideaza_manager_propriu(app):
    from services.project_service import create_project_from_form_data
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            proiect = create_project_from_form_data(form_data=_proiect_form(
                cod_proiect='S13B-M1', manager_id=ids['manager_a']))
            assert proiect.manager_id == ids['manager_a']


def test_create_respinge_manager_strain_404(app):
    from services.project_service import create_project_from_form_data
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            with pytest.raises(HTTPException) as exc:
                create_project_from_form_data(form_data=_proiect_form(
                    cod_proiect='S13B-M2', manager_id=ids['manager_b']))
            assert exc.value.code == 404


def test_create_commit_persista(app):
    from models import Proiect
    from services.project_service import create_project_from_form_data
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        with app.test_request_context('/'):
            create_project_from_form_data(form_data=_proiect_form(cod_proiect='S13B-C1'))
        assert Proiect.query.filter_by(cod_proiect='S13B-C1').first() is not None


def test_update_mapare_campuri(app):
    from services.project_service import update_project_from_form_data
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            from models import Proiect
            proiect = Proiect.query.get(ids['proiect_a'])
            update_project_from_form_data(project=proiect, form_data=_proiect_form(
                cod_proiect='S13A-PA1', nume='Redenumit', status='suspendat',
                data_sfarsit_real=date(2026, 5, 5), buget_total=777))
            assert proiect.nume == 'Redenumit'
            assert proiect.status == 'suspendat'
            assert proiect.data_sfarsit_real == date(2026, 5, 5)
            assert float(proiect.buget_total) == 777.0


def test_update_compune_locatie(app):
    from services.project_service import update_project_from_form_data
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            from models import Proiect
            proiect = Proiect.query.get(ids['proiect_a'])
            update_project_from_form_data(project=proiect, form_data=_proiect_form(
                cod_proiect='S13A-PA1', judet='Iasi', localitate='Iasi'))
            assert proiect.locatie == 'Iasi, Iasi'


def test_update_respinge_manager_strain_404(app):
    from services.project_service import update_project_from_form_data
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            from models import Proiect
            proiect = Proiect.query.get(ids['proiect_a'])
            with pytest.raises(HTTPException) as exc:
                update_project_from_form_data(project=proiect, form_data=_proiect_form(
                    cod_proiect='S13A-PA1', manager_id=ids['manager_b']))
            assert exc.value.code == 404


def test_update_commit_persista(app):
    from models import Proiect
    from services.project_service import update_project_from_form_data
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        with app.test_request_context('/'):
            proiect = Proiect.query.get(ids['proiect_a'])
            update_project_from_form_data(project=proiect, form_data=_proiect_form(
                cod_proiect='S13A-PA1', nume='PersistTest'))
        assert Proiect.query.get(ids['proiect_a']).nume == 'PersistTest'


def test_status_valid_seteaza_si_returneaza(app):
    from services.project_service import change_project_status
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        with app.test_request_context('/'):
            from models import Proiect
            proiect = Proiect.query.get(ids['proiect_a'])
            rez = change_project_status(project=proiect, new_status='suspendat')
            assert rez == {'success': True, 'status': 'suspendat'}
            assert proiect.status == 'suspendat'


def test_status_invalid_rezultat_400_fara_mutatie(app):
    from services.project_service import change_project_status
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        with app.test_request_context('/'):
            from models import Proiect
            proiect = Proiect.query.get(ids['proiect_a'])
            status_initial = proiect.status
            rez = change_project_status(project=proiect, new_status='inexistent')
            assert rez['success'] is False
            assert rez['error'] == 'Status invalid'
            assert rez['status_code'] == 400
            assert proiect.status == status_initial  # fara mutatie


def test_status_finalizat_seteaza_data_sfarsit_real(app):
    from services.project_service import change_project_status
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        with app.test_request_context('/'):
            from models import Proiect
            proiect = Proiect.query.get(ids['proiect_a'])
            proiect.data_sfarsit_real = None
            rez = change_project_status(project=proiect, new_status='finalizat')
            assert rez['success'] is True
            assert proiect.data_sfarsit_real == date.today()


def test_status_finalizat_nu_suprascrie_data_existenta(app):
    from services.project_service import change_project_status
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        with app.test_request_context('/'):
            from models import Proiect
            proiect = Proiect.query.get(ids['proiect_a'])
            proiect.data_sfarsit_real = date(2025, 1, 1)
            change_project_status(project=proiect, new_status='finalizat')
            assert proiect.data_sfarsit_real == date(2025, 1, 1)  # neschimbat


def test_mutating_helpers_un_singur_commit_si_fara_query_brut(app):
    """Guard: fiecare salvare face exact un commit; fara query brut tenant-owned."""
    import inspect
    import services.project_service as svc

    for fn_name in ('create_project_from_form_data',
                    'update_project_from_form_data', 'change_project_status'):
        s = inspect.getsource(getattr(svc, fn_name))
        assert s.count('db.session.commit') == 1, fn_name
        assert 'db.session.rollback' not in s, fn_name
        assert 'Proiect.query' not in s, fn_name
        assert 'Pontaj.query' not in s, fn_name
        assert 'Angajat.query' not in s, fn_name


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
            Proiect.cod_proiect.like('S13%')).all()]
        ang_ids = [a.id for a in Angajat.query.filter(Angajat.nume.like('S13A-%')).all()]
        if prj_ids:
            for p in Pontaj.query.filter(Pontaj.proiect_id.in_(prj_ids)).all():
                db.session.delete(p)
            for ap in AngajatProiect.query.filter(
                AngajatProiect.proiect_id.in_(prj_ids)).all():
                db.session.delete(ap)
        for proiect in Proiect.query.filter(Proiect.cod_proiect.like('S13%')).all():
            db.session.delete(proiect)
        for ang in Angajat.query.filter(Angajat.nume.like('S13A-%')).all():
            db.session.delete(ang)
        for u in Utilizator.query.filter(Utilizator.email.like('s13a-%')).all():
            db.session.delete(u)
        for tenant in Tenant.query.filter(Tenant.cod.like('test-s13a-%')).all():
            db.session.delete(tenant)
        db.session.commit()
