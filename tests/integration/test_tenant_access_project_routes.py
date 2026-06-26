"""Teste tenant access pentru rutele principale de proiect."""

from datetime import date

import pytest


COD_A = 'TA-PROJ-A'
COD_B = 'TA-PROJ-B'
COD_CREATE = 'TA-PROJ-CREATE'


@pytest.fixture(autouse=True)
def curata_project_tenant_access(app):
    _curata_date(app)
    yield
    _curata_date(app)


def test_lista_mode_off_arata_toate_proiectele(authenticated_client, app):
    _creeaza_date(app)
    app.config['MULTI_TENANT_MODE'] = 'off'

    raspuns = authenticated_client.get('/proiecte/')

    assert raspuns.status_code == 200
    assert b'Tenant Proiect A' in raspuns.data
    assert b'Tenant Proiect B' in raspuns.data


def test_detalii_mode_off_functioneaza(authenticated_client, app):
    ids = _creeaza_date(app)
    app.config['MULTI_TENANT_MODE'] = 'off'

    raspuns = authenticated_client.get(f'/proiecte/{ids["proiect_b"]}')

    assert raspuns.status_code == 200
    assert b'Tenant Proiect B' in raspuns.data


def test_hub_mode_off_functioneaza(authenticated_client, app):
    ids = _creeaza_date(app)
    app.config['MULTI_TENANT_MODE'] = 'off'

    raspuns = authenticated_client.get(f'/proiecte/{ids["proiect_b"]}/hub')

    assert raspuns.status_code == 200
    assert b'Tenant Proiect B' in raspuns.data


def test_export_excel_mode_off_functioneaza(authenticated_client, app):
    ids = _creeaza_date(app)
    app.config['MULTI_TENANT_MODE'] = 'off'

    raspuns = authenticated_client.get(f'/proiecte/{ids["proiect_b"]}/export-excel')

    assert raspuns.status_code == 200
    assert raspuns.mimetype == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def test_strict_lista_arata_doar_proiectele_tenantului(authenticated_client, app, admin_user):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.get('/proiecte/')

    assert raspuns.status_code == 200
    assert b'Tenant Proiect A' in raspuns.data
    assert b'Tenant Proiect B' not in raspuns.data


def test_strict_blocheaza_detalii_proiect_strain(authenticated_client, app, admin_user):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.get(f'/proiecte/{ids["proiect_b"]}')

    assert raspuns.status_code == 404


def test_strict_blocheaza_hub_proiect_strain(authenticated_client, app, admin_user):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.get(f'/proiecte/{ids["proiect_b"]}/hub')

    assert raspuns.status_code == 404


def test_strict_blocheaza_editare_proiect_strain(authenticated_client, app, admin_user):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.get(f'/proiecte/{ids["proiect_b"]}/editeaza')

    assert raspuns.status_code == 404


def test_strict_blocheaza_schimbare_status_proiect_strain(authenticated_client, app, admin_user):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.post(
        f'/proiecte/{ids["proiect_b"]}/schimba-status',
        json={'status': 'finalizat'},
    )

    assert raspuns.status_code == 404


def test_strict_blocheaza_export_proiect_strain(authenticated_client, app, admin_user):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.get(f'/proiecte/{ids["proiect_b"]}/export-excel')

    assert raspuns.status_code == 404


def test_strict_creare_proiect_asigneaza_tenantul_curent(authenticated_client, app, admin_user):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.post('/proiecte/adauga', data=_form_proiect(COD_CREATE))

    assert raspuns.status_code == 302
    with app.app_context():
        from models import Proiect

        proiect = Proiect.query.filter_by(cod_proiect=COD_CREATE).one()
        assert proiect.tenant_id == ids['tenant_a']


def test_strict_user_normal_fara_tenant_nu_acceseaza_si_nu_creeaza(
    operator_client, app
):
    ids = _creeaza_date(app)
    app.config['MULTI_TENANT_MODE'] = 'strict'

    detalii = operator_client.get(f'/proiecte/{ids["proiect_a"]}')
    creare = operator_client.post('/proiecte/adauga', data=_form_proiect(COD_CREATE))

    assert detalii.status_code == 404
    assert creare.status_code == 403


def test_strict_super_admin_are_acces_explicit_nefiltrat(authenticated_client, app):
    ids = _creeaza_date(app)
    app.config['MULTI_TENANT_MODE'] = 'strict'

    lista = authenticated_client.get('/proiecte/')
    detalii_b = authenticated_client.get(f'/proiecte/{ids["proiect_b"]}')

    assert lista.status_code == 200
    assert b'Tenant Proiect A' in lista.data
    assert b'Tenant Proiect B' in lista.data
    assert detalii_b.status_code == 200


def _creeaza_date(app):
    from models import db, Proiect, Tenant

    with app.app_context():
        tenant_a = Tenant(cod='test-ta-proj-a', nume='Tenant Proiect A')
        tenant_b = Tenant(cod='test-ta-proj-b', nume='Tenant Proiect B')
        db.session.add_all([tenant_a, tenant_b])
        db.session.commit()

        proiect_a = Proiect(
            tenant_id=tenant_a.id,
            cod_proiect=COD_A,
            nume='Tenant Proiect A',
            data_start=date(2026, 1, 1),
            buget_total=1000,
            status='activ',
        )
        proiect_b = Proiect(
            tenant_id=tenant_b.id,
            cod_proiect=COD_B,
            nume='Tenant Proiect B',
            data_start=date(2026, 1, 1),
            buget_total=2000,
            status='activ',
        )
        db.session.add_all([proiect_a, proiect_b])
        db.session.commit()

        return {
            'tenant_a': tenant_a.id,
            'tenant_b': tenant_b.id,
            'proiect_a': proiect_a.id,
            'proiect_b': proiect_b.id,
        }


def _seteaza_tenant_user(app, user_id, tenant_id):
    from models import db, Utilizator

    with app.app_context():
        user = db.session.get(Utilizator, user_id)
        user.tenant_id = tenant_id
        db.session.commit()


def _form_proiect(cod):
    return {
        'cod_proiect': cod,
        'nume': f'Proiect {cod}',
        'descriere': '',
        'judet': 'Bucuresti',
        'localitate': 'Bucuresti',
        'adresa_santier': '',
        'beneficiar': '',
        'nr_contract_beneficiar': '',
        'data_start': '2026-01-01',
        'data_sfarsit_planificat': '',
        'data_sfarsit_real': '',
        'manager_id': '0',
        'status': 'activ',
        'buget_total': '',
        'buget_manopera': '',
    }


def _curata_date(app):
    from models import db, Proiect, Tenant, Utilizator

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'

        for user in Utilizator.query.filter(Utilizator.email.in_([
            'admin_test@test.local',
            'operator_test@test.local',
        ])).all():
            user.tenant_id = None

        for proiect in Proiect.query.filter(Proiect.cod_proiect.like('TA-PROJ-%')).all():
            db.session.delete(proiect)

        for tenant in Tenant.query.filter(Tenant.cod.like('test-ta-proj-%')).all():
            db.session.delete(tenant)

        db.session.commit()

