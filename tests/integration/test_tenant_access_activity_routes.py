"""Teste tenant access pentru rutele principale de activitati."""

from datetime import date

import pytest


TITLU_A = 'TA_ACT_ROUTE_A'
TITLU_B = 'TA_ACT_ROUTE_B'
TITLU_CREATE = 'TA_ACT_ROUTE_CREATE'
CNP_A = '7900202010101'
CNP_B = '7900202010102'
COD_PROIECT_A = 'TA-ACT-R-P-A'
COD_PROIECT_B = 'TA-ACT-R-P-B'


@pytest.fixture(autouse=True)
def curata_activity_tenant_routes(app):
    _curata_date(app)
    yield
    _curata_date(app)


def test_mode_off_panou_arata_toate_activitatile(authenticated_client, app):
    _creeaza_date(app)
    app.config['MULTI_TENANT_MODE'] = 'off'

    raspuns = authenticated_client.get('/activitati/')

    assert raspuns.status_code == 200
    assert TITLU_A.encode() in raspuns.data
    assert TITLU_B.encode() in raspuns.data


def test_mode_off_detaliu_functioneaza(authenticated_client, app):
    ids = _creeaza_date(app)
    app.config['MULTI_TENANT_MODE'] = 'off'

    raspuns = authenticated_client.get(f'/activitati/{ids["activitate_b"]}')

    assert raspuns.status_code == 200
    assert TITLU_B.encode() in raspuns.data


def test_strict_tenant_vede_doar_activitatile_sale_in_panou(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.get('/activitati/')

    assert raspuns.status_code == 200
    assert TITLU_A.encode() in raspuns.data
    assert TITLU_B.encode() not in raspuns.data


def test_strict_tenant_poate_vedea_detaliu_activitate_proprie(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.get(f'/activitati/{ids["activitate_a"]}')

    assert raspuns.status_code == 200
    assert TITLU_A.encode() in raspuns.data


def test_strict_tenant_nu_poate_vedea_detaliu_activitate_straina(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.get(f'/activitati/{ids["activitate_b"]}')

    assert raspuns.status_code == 404


def test_strict_tenant_nu_poate_edita_activitate_straina(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.get(f'/activitati/{ids["activitate_b"]}/editeaza')

    assert raspuns.status_code == 404


def test_strict_tenant_nu_poate_trimite_activitate_straina(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.post(f'/activitati/{ids["activitate_b"]}/trimite')

    assert raspuns.status_code == 404


def test_strict_tenant_nu_poate_aproba_activitate_straina(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.post(f'/activitati/{ids["activitate_b"]}/aproba')

    assert raspuns.status_code == 404


def test_strict_tenant_nu_poate_respinge_activitate_straina(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.post(
        f'/activitati/{ids["activitate_b"]}/respinge',
        data={'motiv_respingere': 'Tenant strain'},
    )

    assert raspuns.status_code == 404


def test_strict_tenant_nu_poate_sterge_activitate_straina(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.post(f'/activitati/{ids["activitate_b"]}/sterge')

    assert raspuns.status_code == 404


def test_strict_panou_aprobare_arata_doar_activitatile_tenantului(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.get('/activitati/aprobare')

    assert raspuns.status_code == 200
    assert TITLU_A.encode() in raspuns.data
    assert TITLU_B.encode() not in raspuns.data


def test_strict_aprobare_masa_mixta_este_respinsa_integral(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.post('/activitati/aprobare/masa', data={
        'activitate_ids[]': [str(ids['activitate_a']), str(ids['activitate_b'])],
        'actiune': 'aproba',
    })

    assert raspuns.status_code == 404
    with app.app_context():
        from models import RaportActivitate

        activitate_a = RaportActivitate.query.get(ids['activitate_a'])
        activitate_b = RaportActivitate.query.get(ids['activitate_b'])
        assert activitate_a.status == 'trimis'
        assert activitate_b.status == 'trimis'


def test_strict_creare_respinge_proiect_strain(authenticated_client, app, admin_user):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.post('/activitati/adauga', data=_form_activitate(
        ids['angajat_a'],
        ids['proiect_b'],
        TITLU_CREATE,
    ))

    assert raspuns.status_code == 404
    with app.app_context():
        from models import RaportActivitate

        assert RaportActivitate.query.filter_by(activitate_principala=TITLU_CREATE).first() is None


def test_strict_creare_respinge_angajat_strain(authenticated_client, app, admin_user):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.post('/activitati/adauga', data=_form_activitate(
        ids['angajat_b'],
        ids['proiect_a'],
        TITLU_CREATE,
    ))

    assert raspuns.status_code == 404
    with app.app_context():
        from models import RaportActivitate

        assert RaportActivitate.query.filter_by(activitate_principala=TITLU_CREATE).first() is None


def test_strict_user_normal_fara_tenant_nu_acceseaza_activitate(
    operator_client, app
):
    ids = _creeaza_date(app)
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = operator_client.get(f'/activitati/{ids["activitate_a"]}')

    assert raspuns.status_code == 404


def test_optional_cu_tenant_filtreaza_activitatile(authenticated_client, app, admin_user):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'optional'

    detaliu_strain = authenticated_client.get(f'/activitati/{ids["activitate_b"]}')
    panou = authenticated_client.get('/activitati/')

    assert detaliu_strain.status_code == 404
    assert TITLU_A.encode() in panou.data
    assert TITLU_B.encode() not in panou.data


def test_optional_fara_tenant_pastreaza_comportamentul_de_migrare(
    authenticated_client, app
):
    _creeaza_date(app)
    app.config['MULTI_TENANT_MODE'] = 'optional'

    panou = authenticated_client.get('/activitati/')

    assert panou.status_code == 200
    assert TITLU_A.encode() in panou.data
    assert TITLU_B.encode() in panou.data


def test_strict_export_preview_este_tenant_scoped(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.get('/activitati/export/preview?luna=2026-01')

    assert raspuns.status_code == 200
    assert TITLU_A.encode() in raspuns.data
    assert TITLU_B.encode() not in raspuns.data


def test_strict_export_respinge_angajat_strain_inainte_de_generare(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.get(
        f'/activitati/export?luna=2026-01&angajat_id={ids["angajat_b"]}'
    )

    assert raspuns.status_code == 302
    assert raspuns.mimetype == 'text/html'


def test_strict_super_admin_are_acces_explicit_nefiltrat(authenticated_client, app):
    ids = _creeaza_date(app)
    app.config['MULTI_TENANT_MODE'] = 'strict'

    panou = authenticated_client.get('/activitati/')
    detaliu_b = authenticated_client.get(f'/activitati/{ids["activitate_b"]}')

    assert panou.status_code == 200
    assert TITLU_A.encode() in panou.data
    assert TITLU_B.encode() in panou.data
    assert detaliu_b.status_code == 200


def _creeaza_date(app):
    from models import db, Angajat, Proiect, RaportActivitate, Tenant

    with app.app_context():
        tenant_a = Tenant(cod='test-ta-act-route-a', nume='Tenant Act Route A')
        tenant_b = Tenant(cod='test-ta-act-route-b', nume='Tenant Act Route B')
        db.session.add_all([tenant_a, tenant_b])
        db.session.commit()

        proiect_a = Proiect(
            tenant_id=tenant_a.id,
            cod_proiect=COD_PROIECT_A,
            nume='Tenant Act Route Project A',
            data_start=date(2026, 1, 1),
            status='activ',
        )
        proiect_b = Proiect(
            tenant_id=tenant_b.id,
            cod_proiect=COD_PROIECT_B,
            nume='Tenant Act Route Project B',
            data_start=date(2026, 1, 1),
            status='activ',
        )
        angajat_a = Angajat(
            tenant_id=tenant_a.id,
            nume='TenantA',
            prenume='RutaActivitate',
            cnp=CNP_A,
            functie='Inginer',
            data_angajare=date(2026, 1, 1),
            status='activ',
        )
        angajat_b = Angajat(
            tenant_id=tenant_b.id,
            nume='TenantB',
            prenume='RutaActivitate',
            cnp=CNP_B,
            functie='Inginer',
            data_angajare=date(2026, 1, 1),
            status='activ',
        )
        db.session.add_all([proiect_a, proiect_b, angajat_a, angajat_b])
        db.session.commit()

        activitate_a = RaportActivitate(
            angajat_id=angajat_a.id,
            proiect_id=proiect_a.id,
            proiecte_ids=str([proiect_a.id]),
            data=date(2026, 1, 2),
            activitate_principala=TITLU_A,
            tip_activitate='zilnica',
            status='trimis',
        )
        activitate_b = RaportActivitate(
            angajat_id=angajat_b.id,
            proiect_id=proiect_b.id,
            proiecte_ids=str([proiect_b.id]),
            data=date(2026, 1, 2),
            activitate_principala=TITLU_B,
            tip_activitate='zilnica',
            status='trimis',
        )
        db.session.add_all([activitate_a, activitate_b])
        db.session.commit()

        return {
            'tenant_a': tenant_a.id,
            'tenant_b': tenant_b.id,
            'proiect_a': proiect_a.id,
            'proiect_b': proiect_b.id,
            'angajat_a': angajat_a.id,
            'angajat_b': angajat_b.id,
            'activitate_a': activitate_a.id,
            'activitate_b': activitate_b.id,
        }


def _seteaza_tenant_user(app, user_id, tenant_id):
    from models import db, Utilizator

    with app.app_context():
        user = db.session.get(Utilizator, user_id)
        user.tenant_id = tenant_id
        db.session.commit()


def _form_activitate(angajat_id, proiect_id, titlu):
    return {
        'angajat_id': str(angajat_id),
        'proiect_ids[]': [str(proiect_id)],
        'data': '2026-01-03',
        'tip_activitate': 'zilnica',
        'activitate_principala': titlu,
        'status_executie': 'planificata',
        'actiune': 'draft',
    }


def _curata_date(app):
    from models import db, Angajat, Proiect, RaportActivitate, Tenant, Utilizator

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'

        for user in Utilizator.query.filter(Utilizator.email.in_([
            'admin_test@test.local',
            'operator_test@test.local',
        ])).all():
            user.tenant_id = None

        RaportActivitate.query.filter(
            RaportActivitate.activitate_principala.in_([
                TITLU_A,
                TITLU_B,
                TITLU_CREATE,
            ])
        ).delete(synchronize_session=False)
        Proiect.query.filter(Proiect.cod_proiect.like('TA-ACT-R-%')).delete(synchronize_session=False)
        Angajat.query.filter(Angajat.cnp.in_([CNP_A, CNP_B])).delete(synchronize_session=False)
        Tenant.query.filter(Tenant.cod.like('test-ta-act-route-%')).delete(synchronize_session=False)
        db.session.commit()
