"""Teste directe pentru services/timesheet_service.py (S1.2A).

Verifica calculul pur de ore + contextul de citire/listare tenant-safe:
scoping pe tenant (list/daily/calendar/approval/duplicate/project-employees),
comportament pe moduri (off/strict) si fail-closed pentru user fara tenant.
"""

from datetime import date

import pytest
from werkzeug.exceptions import HTTPException


class _FakeUser:
    def __init__(self, user_id=777):
        self.id = user_id


class _Field:
    def __init__(self, data):
        self.data = data


def _form_pontaj(*, angajat_id, proiect_id, data_pontaj, ora_start='08:00',
                 ora_sfarsit='16:00', tip_zi='lucratoare', observatii='',
                 actiune='draft'):
    class _Form:
        pass

    form = _Form()
    form.angajat_id = _Field(angajat_id)
    form.proiect_id = _Field(proiect_id)
    form.data = _Field(data_pontaj)
    form.ora_start = _Field(ora_start)
    form.ora_sfarsit = _Field(ora_sfarsit)
    form.tip_zi = _Field(tip_zi)
    form.observatii = _Field(observatii)
    form.actiune = _Field(actiune)
    return form


@pytest.fixture(autouse=True)
def curata_s12a(app):
    _curata(app)
    yield
    _curata(app)


# ============================================================
# calculate_timesheet_hours — calcul pur (identic cu calculate_hours)
# ============================================================

def test_calc_zi_normala(app):
    from services.timesheet_service import calculate_timesheet_hours
    with app.app_context():
        r = calculate_timesheet_hours(ora_start='08:00', ora_sfarsit='16:00',
                                      tip_zi='lucratoare', data_pontaj=None)
    # 8h - 30min pauza = 7.5h, toate normale
    assert r['ore_lucrate'] == 7.5
    assert r['ore_normale'] == 7.5
    assert r['ore_supl_50'] == 0
    assert r['ore_supl_100'] == 0
    assert r['tip_zi'] == 'lucratoare'


def test_calc_tura_noapte(app):
    from services.timesheet_service import calculate_timesheet_hours
    with app.app_context():
        r = calculate_timesheet_hours(ora_start='22:00', ora_sfarsit='06:00',
                                      tip_zi='lucratoare', data_pontaj=None)
    assert r['ore_lucrate'] == 7.5  # 480min - 30 pauza


def test_calc_ore_invalide(app):
    from services.timesheet_service import calculate_timesheet_hours
    with app.app_context():
        r = calculate_timesheet_hours(ora_start='bad', ora_sfarsit='x',
                                      tip_zi='lucratoare', data_pontaj=None)
    assert r == {'ore_lucrate': 0, 'ore_normale': 0, 'ore_supl_50': 0, 'ore_supl_100': 0}


def test_calc_suplimentare_si_cap_12h(app):
    from services.timesheet_service import calculate_timesheet_hours
    with app.app_context():
        # 06:00-22:00 = 960min -> cap 720 -> -30 = 690 -> 11.5h
        r = calculate_timesheet_hours(ora_start='06:00', ora_sfarsit='22:00',
                                      tip_zi='lucratoare', data_pontaj=None)
    assert r['ore_lucrate'] == 11.5
    assert r['ore_normale'] == 8
    assert r['ore_supl_50'] == 2
    assert r['ore_supl_100'] == 1.5


# ============================================================
# Context tenant-safe
# ============================================================

def test_list_context_doar_tenant_curent(app):
    from services.timesheet_service import get_timesheet_list_context
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        pa = _pontaj(app, angajat_id=ids['ang_a'], proiect_id=ids['proiect_a'])
        pb = _pontaj(app, angajat_id=ids['ang_b'], proiect_id=ids['proiect_b'])
        with app.test_request_context('/'):
            from flask import g
            g.tenant_override = ids['tenant_a']
            ctx = get_timesheet_list_context(filters={})
        ids_vazute = {p.id for p in ctx['pontaje']}
        assert pa in ids_vazute
        assert pb not in ids_vazute


def test_daily_rows_doar_tenant_curent(app):
    from services.timesheet_service import get_daily_timesheet_rows
    ids = _seed(app)
    zi = date(2026, 4, 6)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        _pontaj(app, angajat_id=ids['ang_a'], proiect_id=ids['proiect_a'], data=zi)
        _pontaj(app, angajat_id=ids['ang_b'], proiect_id=ids['proiect_b'], data=zi)
        with app.test_request_context('/'):
            from flask import g
            g.tenant_override = ids['tenant_a']
            rows = get_daily_timesheet_rows(date_value=zi)
        nume = {r['angajat'] for r in rows}
        assert any('S12A-A' in n for n in nume)
        assert not any('S12A-B' in n for n in nume)


def test_calendar_context_doar_tenant_curent(app):
    from services.timesheet_service import get_timesheet_calendar_context
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        _pontaj(app, angajat_id=ids['ang_a'], proiect_id=ids['proiect_a'],
                data=date(2026, 4, 6), ore_lucrate=8)
        with app.test_request_context('/'):
            from flask import g
            g.tenant_override = ids['tenant_a']
            ctx = get_timesheet_calendar_context(angajat_id=ids['ang_a'], luna=4, anul=2026)
        # ziua 6 trebuie marcata 'prezent'
        zi6 = next(c for c in ctx['calendar_data'] if c['zi'] == 6)
        assert zi6['tip'] == 'prezent'
        assert ctx['stats']['zile_lucrate'] == 1


def test_calendar_context_angajat_strain_nu_apare(app):
    from services.timesheet_service import get_timesheet_calendar_context
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        _pontaj(app, angajat_id=ids['ang_b'], proiect_id=ids['proiect_b'],
                data=date(2026, 4, 6), ore_lucrate=8)
        with app.test_request_context('/'):
            from flask import g
            g.tenant_override = ids['tenant_a']
            # cerem calendarul angajatului strain B din tenant curent A
            ctx = get_timesheet_calendar_context(angajat_id=ids['ang_b'], luna=4, anul=2026)
        assert ctx['angajat'] is None  # angajat strain invizibil
        zi6 = next(c for c in ctx['calendar_data'] if c['zi'] == 6)
        assert zi6['tip'] != 'prezent'  # pontajul strain nu este agregat


def test_approval_context_doar_trimise_tenant_curent(app):
    from services.timesheet_service import get_timesheet_approval_context
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        pa = _pontaj(app, angajat_id=ids['ang_a'], proiect_id=ids['proiect_a'], status='trimis')
        _pontaj(app, angajat_id=ids['ang_a'], proiect_id=ids['proiect_a'], status='draft',
                data=date(2026, 4, 7))
        pb = _pontaj(app, angajat_id=ids['ang_b'], proiect_id=ids['proiect_b'], status='trimis')
        with app.test_request_context('/'):
            from flask import g
            g.tenant_override = ids['tenant_a']
            ctx = get_timesheet_approval_context(filters={})
        vazute = {p.id for p in ctx['pontaje']}
        assert pa in vazute        # trimis, tenant A
        assert pb not in vazute    # trimis, dar tenant B


def test_project_employees_proiect_strain_404(app):
    from services.timesheet_service import get_project_employees_for_timesheet
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            from flask import g
            g.tenant_override = ids['tenant_a']
            with pytest.raises(HTTPException) as exc:
                get_project_employees_for_timesheet(project_id=ids['proiect_b'])
        assert exc.value.code == 404


def test_project_employees_exclude_angajat_strain(app):
    from services.timesheet_service import get_project_employees_for_timesheet
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        _aloca(app, angajat_id=ids['ang_a'], proiect_id=ids['proiect_a'])
        # contaminare: angajat din tenant B alocat la proiect A
        _aloca(app, angajat_id=ids['ang_b'], proiect_id=ids['proiect_a'])
        with app.test_request_context('/'):
            from flask import g
            g.tenant_override = ids['tenant_a']
            rezultat = get_project_employees_for_timesheet(project_id=ids['proiect_a'])
        rez_ids = {r['id'] for r in rezultat}
        assert ids['ang_a'] in rez_ids
        assert ids['ang_b'] not in rez_ids  # angajat strain exclus


def test_duplicate_check_tenant_scoped(app):
    from services.timesheet_service import check_timesheet_duplicate
    ids = _seed(app)
    zi = date(2026, 4, 8)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        _pontaj(app, angajat_id=ids['ang_a'], proiect_id=ids['proiect_a'], data=zi)
        with app.test_request_context('/'):
            from flask import g
            g.tenant_override = ids['tenant_a']
            r_a = check_timesheet_duplicate(employee_id=ids['ang_a'], date_value=zi)
            r_b = check_timesheet_duplicate(employee_id=ids['ang_b'], date_value=zi)
        assert r_a['exists'] is True
        assert r_b['exists'] is False  # angajat strain -> fara leak


def test_off_mode_vede_ambii_tenanti(app):
    from services.timesheet_service import get_timesheet_list_context
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        pa = _pontaj(app, angajat_id=ids['ang_a'], proiect_id=ids['proiect_a'])
        pb = _pontaj(app, angajat_id=ids['ang_b'], proiect_id=ids['proiect_b'])
        with app.test_request_context('/'):
            ctx = get_timesheet_list_context(filters={})
        vazute = {p.id for p in ctx['pontaje']}
        assert pa in vazute
        assert pb in vazute  # off => nefiltrat


def test_strict_fara_tenant_fail_closed(app):
    from services.timesheet_service import get_timesheet_list_context
    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        _pontaj(app, angajat_id=ids['ang_a'], proiect_id=ids['proiect_a'])
        with app.test_request_context('/'):
            ctx = get_timesheet_list_context(filters={})
        assert ctx['pontaje'] == []  # fail closed
        assert ctx['angajati'] == []
        assert ctx['proiecte'] == []


def test_read_helpers_fara_query_brut(app):
    """Guard: helperii de citire nu folosesc query brut tenant-owned."""
    import inspect
    import services.timesheet_service as svc

    for fn_name in ('get_timesheet_list_context', 'get_daily_timesheet_rows',
                    'get_timesheet_calendar_context', 'get_timesheet_approval_context',
                    'check_timesheet_duplicate'):
        sursa = inspect.getsource(getattr(svc, fn_name))
        assert 'Pontaj.query.' not in sursa, fn_name
        assert 'Angajat.query.' not in sursa, fn_name
        assert 'Proiect.query.' not in sursa, fn_name


# ============================================================
# S1.2B1 — save single create/edit (HTTP-free, tenant-safe)
# ============================================================

def test_create_single_pontaj_cu_campurile_corecte(app):
    from services.timesheet_service import create_timesheet_from_form_data
    from models import Pontaj

    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        with app.test_request_context('/'):
            rezultat = create_timesheet_from_form_data(
                form_data=_form_pontaj(
                    angajat_id=ids['ang_a'],
                    proiect_id=ids['proiect_a'],
                    data_pontaj=date(2026, 4, 10),
                    observatii='TEST_S12A_CREATE',
                ),
                current_user=_FakeUser(user_id=901),
            )

        pontaj = Pontaj.query.get(rezultat['timesheet'].id)
        assert rezultat['created'] is True
        assert rezultat['duplicate'] is False
        assert pontaj.angajat_id == ids['ang_a']
        assert pontaj.proiect_id == ids['proiect_a']
        assert pontaj.data == date(2026, 4, 10)
        assert pontaj.ora_start == '08:00'
        assert pontaj.ora_sfarsit == '16:00'
        assert float(pontaj.ore_lucrate) == 7.5
        assert float(pontaj.ore_normale) == 7.5
        assert float(pontaj.ore_suplimentare_50) == 0
        assert float(pontaj.ore_suplimentare_100) == 0
        assert pontaj.tip_zi == 'lucratoare'
        assert pontaj.status == 'draft'
        assert pontaj.observatii == 'TEST_S12A_CREATE'
        assert pontaj.introdus_de == 901


def test_create_single_pontaj_status_trimis(app):
    from services.timesheet_service import create_timesheet_from_form_data

    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        with app.test_request_context('/'):
            rezultat = create_timesheet_from_form_data(
                form_data=_form_pontaj(
                    angajat_id=ids['ang_a'],
                    proiect_id=ids['proiect_a'],
                    data_pontaj=date(2026, 4, 11),
                    observatii='TEST_S12A_CREATE_TRIMIS',
                    actiune='trimite',
                ),
                current_user=_FakeUser(),
            )

        assert rezultat['timesheet'].status == 'trimis'


def test_create_single_pontaj_duplicat_nu_muteaza(app):
    from services.timesheet_service import create_timesheet_from_form_data
    from models import Pontaj

    ids = _seed(app)
    zi = date(2026, 4, 12)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        _pontaj(app, angajat_id=ids['ang_a'], proiect_id=ids['proiect_a'], data=zi)
        inainte = Pontaj.query.filter_by(angajat_id=ids['ang_a'], data=zi).count()
        with app.test_request_context('/'):
            rezultat = create_timesheet_from_form_data(
                form_data=_form_pontaj(
                    angajat_id=ids['ang_a'],
                    proiect_id=ids['proiect_a'],
                    data_pontaj=zi,
                    observatii='TEST_S12A_DUP_CREATE',
                ),
                current_user=_FakeUser(),
            )
        dupa = Pontaj.query.filter_by(angajat_id=ids['ang_a'], data=zi).count()

        assert rezultat['duplicate'] is True
        assert rezultat['created'] is False
        assert dupa == inainte


def test_create_single_respinge_angajat_sau_proiect_strain(app):
    from services.timesheet_service import create_timesheet_from_form_data
    from models import Pontaj
    from flask import g

    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            with pytest.raises(HTTPException) as exc_proiect:
                create_timesheet_from_form_data(
                    form_data=_form_pontaj(
                        angajat_id=ids['ang_a'],
                        proiect_id=ids['proiect_b'],
                        data_pontaj=date(2026, 4, 13),
                        observatii='TEST_S12A_FOREIGN_PROJECT',
                    ),
                    current_user=_FakeUser(),
                )
            with pytest.raises(HTTPException) as exc_angajat:
                create_timesheet_from_form_data(
                    form_data=_form_pontaj(
                        angajat_id=ids['ang_b'],
                        proiect_id=ids['proiect_a'],
                        data_pontaj=date(2026, 4, 14),
                        observatii='TEST_S12A_FOREIGN_EMPLOYEE',
                    ),
                    current_user=_FakeUser(),
                )

        assert exc_proiect.value.code == 404
        assert exc_angajat.value.code == 404
        assert Pontaj.query.filter(Pontaj.observatii.like('TEST_S12A_FOREIGN%')).count() == 0


def test_create_single_strict_fara_tenant_fail_closed(app):
    from services.timesheet_service import create_timesheet_from_form_data
    from models import Pontaj

    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            with pytest.raises(HTTPException) as exc:
                create_timesheet_from_form_data(
                    form_data=_form_pontaj(
                        angajat_id=ids['ang_a'],
                        proiect_id=ids['proiect_a'],
                        data_pontaj=date(2026, 4, 15),
                        observatii='TEST_S12A_STRICT_NO_TENANT',
                    ),
                    current_user=_FakeUser(),
                )

        assert exc.value.code == 403
        assert Pontaj.query.filter_by(observatii='TEST_S12A_STRICT_NO_TENANT').first() is None


def test_update_single_pontaj_cu_campurile_corecte_si_status_pastrat(app):
    from services.timesheet_service import update_timesheet_from_form_data
    from models import Pontaj, db

    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        pid = _pontaj(app, angajat_id=ids['ang_a'], proiect_id=ids['proiect_a'],
                      data=date(2026, 4, 16), status='respins')
        pontaj = Pontaj.query.get(pid)
        pontaj.aprobat_de = 321
        db.session.commit()

        with app.test_request_context('/'):
            rezultat = update_timesheet_from_form_data(
                timesheet=pontaj,
                form_data=_form_pontaj(
                    angajat_id=ids['ang_a'],
                    proiect_id=ids['proiect_a'],
                    data_pontaj=date(2026, 4, 17),
                    ora_start='07:00',
                    ora_sfarsit='18:00',
                    observatii='TEST_S12A_EDITED',
                    actiune='draft',
                ),
                current_user=_FakeUser(),
            )

        assert rezultat['updated'] is True
        assert rezultat['duplicate'] is False
        assert pontaj.data == date(2026, 4, 17)
        assert pontaj.ora_start == '07:00'
        assert pontaj.ora_sfarsit == '18:00'
        assert float(pontaj.ore_lucrate) == 10.5
        assert float(pontaj.ore_normale) == 8
        assert float(pontaj.ore_suplimentare_50) == 2
        assert float(pontaj.ore_suplimentare_100) == 0.5
        assert pontaj.observatii == 'TEST_S12A_EDITED'
        assert pontaj.status == 'respins'
        assert pontaj.aprobat_de == 321


def test_update_single_pontaj_trimite_schimba_status(app):
    from services.timesheet_service import update_timesheet_from_form_data
    from models import Pontaj

    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        pid = _pontaj(app, angajat_id=ids['ang_a'], proiect_id=ids['proiect_a'],
                      data=date(2026, 4, 18), status='draft')
        pontaj = Pontaj.query.get(pid)
        with app.test_request_context('/'):
            update_timesheet_from_form_data(
                timesheet=pontaj,
                form_data=_form_pontaj(
                    angajat_id=ids['ang_a'],
                    proiect_id=ids['proiect_a'],
                    data_pontaj=date(2026, 4, 18),
                    observatii='TEST_S12A_EDIT_TRIMIS',
                    actiune='trimite',
                ),
                current_user=_FakeUser(),
            )

        assert pontaj.status == 'trimis'


def test_update_single_duplicate_exclude_pontaj_curent(app):
    from services.timesheet_service import update_timesheet_from_form_data
    from models import Pontaj

    ids = _seed(app)
    zi = date(2026, 4, 19)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        pid = _pontaj(app, angajat_id=ids['ang_a'], proiect_id=ids['proiect_a'], data=zi)
        pontaj = Pontaj.query.get(pid)
        with app.test_request_context('/'):
            rezultat = update_timesheet_from_form_data(
                timesheet=pontaj,
                form_data=_form_pontaj(
                    angajat_id=ids['ang_a'],
                    proiect_id=ids['proiect_a'],
                    data_pontaj=zi,
                    observatii='TEST_S12A_EDIT_SAME',
                ),
                current_user=_FakeUser(),
            )

        assert rezultat['duplicate'] is False
        assert pontaj.observatii == 'TEST_S12A_EDIT_SAME'


def test_update_single_duplicate_alt_pontaj_nu_muteaza(app):
    from services.timesheet_service import update_timesheet_from_form_data
    from models import Pontaj

    ids = _seed(app)
    zi_initiala = date(2026, 4, 20)
    zi_duplicat = date(2026, 4, 21)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        pid = _pontaj(app, angajat_id=ids['ang_a'], proiect_id=ids['proiect_a'], data=zi_initiala)
        _pontaj(app, angajat_id=ids['ang_a'], proiect_id=ids['proiect_a'], data=zi_duplicat)
        pontaj = Pontaj.query.get(pid)
        with app.test_request_context('/'):
            rezultat = update_timesheet_from_form_data(
                timesheet=pontaj,
                form_data=_form_pontaj(
                    angajat_id=ids['ang_a'],
                    proiect_id=ids['proiect_a'],
                    data_pontaj=zi_duplicat,
                    observatii='TEST_S12A_EDIT_DUP',
                ),
                current_user=_FakeUser(),
            )

        assert rezultat['duplicate'] is True
        assert rezultat['updated'] is False
        assert pontaj.data == zi_initiala
        assert pontaj.observatii == 'TEST_S12A'


def test_update_single_respinge_angajat_sau_proiect_strain(app):
    from services.timesheet_service import update_timesheet_from_form_data
    from models import Pontaj
    from flask import g

    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        pid = _pontaj(app, angajat_id=ids['ang_a'], proiect_id=ids['proiect_a'],
                      data=date(2026, 4, 22))
        pontaj = Pontaj.query.get(pid)
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            with pytest.raises(HTTPException) as exc_proiect:
                update_timesheet_from_form_data(
                    timesheet=pontaj,
                    form_data=_form_pontaj(
                        angajat_id=ids['ang_a'],
                        proiect_id=ids['proiect_b'],
                        data_pontaj=date(2026, 4, 23),
                    ),
                    current_user=_FakeUser(),
                )
            with pytest.raises(HTTPException) as exc_angajat:
                update_timesheet_from_form_data(
                    timesheet=pontaj,
                    form_data=_form_pontaj(
                        angajat_id=ids['ang_b'],
                        proiect_id=ids['proiect_a'],
                        data_pontaj=date(2026, 4, 23),
                    ),
                    current_user=_FakeUser(),
                )

        assert exc_proiect.value.code == 404
        assert exc_angajat.value.code == 404
        assert pontaj.data == date(2026, 4, 22)


def test_update_target_strain_blocat_de_lookup_ruta(app):
    from services.security.tenant_access import get_timesheet_or_404
    from flask import g

    ids = _seed(app)
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        pontaj_b = _pontaj(app, angajat_id=ids['ang_b'], proiect_id=ids['proiect_b'],
                           data=date(2026, 4, 24))
        with app.test_request_context('/'):
            g.tenant_override = ids['tenant_a']
            with pytest.raises(HTTPException) as exc:
                get_timesheet_or_404(pontaj_b)

        assert exc.value.code == 404


def test_save_helpers_fara_query_brut(app):
    """Guard: helperii S1.2B1 nu introduc query brut tenant-owned."""
    import inspect
    import services.timesheet_service as svc

    for fn_name in ('create_timesheet_from_form_data',
                    'update_timesheet_from_form_data',
                    '_find_timesheet_duplicate',
                    '_validate_timesheet_inputs'):
        sursa = inspect.getsource(getattr(svc, fn_name))
        assert 'Pontaj.query.' not in sursa, fn_name
        assert 'Angajat.query.' not in sursa, fn_name
        assert 'Proiect.query.' not in sursa, fn_name
        assert 'RaportActivitate.query.' not in sursa, fn_name


# ============================================================
# Fixture data
# ============================================================

def _seed(app):
    from models import Angajat, Proiect, Tenant, db
    with app.app_context():
        ta = Tenant(cod='test-s12a-a', nume='Tenant S12A A')
        tb = Tenant(cod='test-s12a-b', nume='Tenant S12A B')
        db.session.add_all([ta, tb])
        db.session.commit()
        pa = Proiect(tenant_id=ta.id, cod_proiect='TEST-S12A-PRJ-A', nume='Proiect A',
                     data_start=date(2026, 1, 1), status='activ')
        pb = Proiect(tenant_id=tb.id, cod_proiect='TEST-S12A-PRJ-B', nume='Proiect B',
                     data_start=date(2026, 1, 1), status='activ')
        db.session.add_all([pa, pb])
        db.session.commit()
        aa = Angajat(tenant_id=ta.id, nume='S12A-A', prenume='Test', cnp='1900012000101',
                     status='activ', data_angajare=date(2026, 1, 1))
        ab = Angajat(tenant_id=tb.id, nume='S12A-B', prenume='Test', cnp='1900012000102',
                     status='activ', data_angajare=date(2026, 1, 1))
        db.session.add_all([aa, ab])
        db.session.commit()
        return {
            'tenant_a': ta.id, 'tenant_b': tb.id,
            'proiect_a': pa.id, 'proiect_b': pb.id,
            'ang_a': aa.id, 'ang_b': ab.id,
        }


def _pontaj(app, *, angajat_id, proiect_id, data=date(2026, 4, 6), status='draft',
            ore_lucrate=8):
    from models import Pontaj, db
    with app.app_context():
        p = Pontaj(angajat_id=angajat_id, proiect_id=proiect_id, data=data,
                   ore_lucrate=ore_lucrate, ore_normale=ore_lucrate, status=status,
                   observatii='TEST_S12A')
        db.session.add(p)
        db.session.commit()
        return p.id


def _aloca(app, *, angajat_id, proiect_id):
    from models import AngajatProiect, db
    with app.app_context():
        ap = AngajatProiect(angajat_id=angajat_id, proiect_id=proiect_id,
                            functie_pe_proiect='TEST_S12A')
        db.session.add(ap)
        db.session.commit()
        return ap.id


def _curata(app):
    from models import Angajat, AngajatProiect, Pontaj, Proiect, Tenant, db
    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        for p in Pontaj.query.filter(Pontaj.observatii.like('TEST_S12A%')).all():
            db.session.delete(p)
        for ap in AngajatProiect.query.filter(
            AngajatProiect.functie_pe_proiect == 'TEST_S12A'
        ).all():
            db.session.delete(ap)
        for ang in Angajat.query.filter(Angajat.nume.like('S12A-%')).all():
            db.session.delete(ang)
        for proiect in Proiect.query.filter(Proiect.cod_proiect.like('TEST-S12A-%')).all():
            db.session.delete(proiect)
        for tenant in Tenant.query.filter(Tenant.cod.like('test-s12a-%')).all():
            db.session.delete(tenant)
        db.session.commit()
