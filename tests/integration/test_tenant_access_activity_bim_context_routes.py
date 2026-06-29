"""Teste tenant access pentru contextul BIM din rutele de activitati."""

from contextlib import contextmanager
from datetime import date

import pytest
from flask import template_rendered


TITLU_A = 'TA_ACT_BIM_R_A'
TITLU_B = 'TA_ACT_BIM_R_B'
TITLU_CONTAMINAT = 'TA_ACT_BIM_R_CONTAMINAT'
TITLU_CREATE = 'TA_ACT_BIM_R_CREATE'
CNP_A = '7900314010101'
CNP_B = '7900314010102'


@pytest.fixture(autouse=True)
def curata_activity_bim_context_routes(app):
    _curata_date(app)
    yield
    _curata_date(app)


def test_strict_panou_si_formular_scopeaza_dropdown_bim(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_admin_tenant(app, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    panou = authenticated_client.get('/activitati/')
    formular = authenticated_client.get('/activitati/adauga')

    assert panou.status_code == 200
    assert formular.status_code == 200
    assert b'TA-ACT-BIM-R-SITE-A' in panou.data
    assert b'TA-ACT-BIM-R-BLD-A' in panou.data
    assert b'TA-ACT-BIM-R-SITE-B' not in panou.data
    assert b'TA-ACT-BIM-R-BLD-B' not in panou.data
    assert b'TA-ACT-BIM-R-SITE-A' in formular.data
    assert b'TA-ACT-BIM-R-SITE-B' not in formular.data


def test_strict_filtru_bim_strain_nu_scurge_date(authenticated_client, app, admin_user):
    ids = _creeaza_date(app)
    _seteaza_admin_tenant(app, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    site_strain = authenticated_client.get(
        f'/activitati/?santier_id={ids["site_b"]}'
    )
    element_strain = authenticated_client.get(
        f'/activitati/?element_bim_id={ids["element_b"]}'
    )

    assert site_strain.status_code == 200
    assert element_strain.status_code == 200
    assert TITLU_A.encode() not in site_strain.data
    assert TITLU_B.encode() not in site_strain.data
    assert TITLU_A.encode() not in element_strain.data
    assert TITLU_B.encode() not in element_strain.data


def test_optional_cu_tenant_scopeaza_dropdown_bim(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_admin_tenant(app, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'optional'

    panou = authenticated_client.get('/activitati/')

    assert panou.status_code == 200
    assert b'TA-ACT-BIM-R-SITE-A' in panou.data
    assert b'TA-ACT-BIM-R-SITE-B' not in panou.data


def test_off_mode_pastreaza_dropdown_bim_legacy(authenticated_client, app):
    _creeaza_date(app)
    app.config['MULTI_TENANT_MODE'] = 'off'

    panou = authenticated_client.get('/activitati/')

    assert panou.status_code == 200
    assert b'TA-ACT-BIM-R-SITE-A' in panou.data
    assert b'TA-ACT-BIM-R-SITE-B' in panou.data


def test_strict_creare_respinge_element_bim_strain(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_admin_tenant(app, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.post('/activitati/adauga', data=_form_activitate(
        ids,
        TITLU_CREATE,
        bim_element_id=ids['element_b'],
    ))

    assert raspuns.status_code == 404
    _assert_activitate_nu_exista(app, TITLU_CREATE)


def test_strict_creare_respinge_spatiu_bim_strain(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_admin_tenant(app, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.post('/activitati/adauga', data=_form_activitate(
        ids,
        TITLU_CREATE,
        bim_spatiu_id=ids['spatiu_b'],
    ))

    assert raspuns.status_code == 404
    _assert_activitate_nu_exista(app, TITLU_CREATE)


def test_strict_creare_respinge_context_bim_mixt(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_admin_tenant(app, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.post('/activitati/adauga', data=_form_activitate(
        ids,
        TITLU_CREATE,
        bim_santier_id=ids['site_a'],
        bim_element_id=ids['element_b'],
    ))

    assert raspuns.status_code == 404
    _assert_activitate_nu_exista(app, TITLU_CREATE)


def test_strict_creare_deriveaza_zona_din_spatiu_tenant_safe(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_admin_tenant(app, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.post('/activitati/adauga', data=_form_activitate(
        ids,
        TITLU_CREATE,
        bim_santier_id=ids['site_a'],
        bim_cladire_id=ids['cladire_a'],
        bim_nivel_id=ids['nivel_a'],
        bim_spatiu_id=ids['spatiu_a'],
        bim_element_id=ids['element_a'],
    ))

    assert raspuns.status_code == 302
    with app.app_context():
        from models import RaportActivitate

        activitate = RaportActivitate.query.filter_by(
            activitate_principala=TITLU_CREATE
        ).first()
        assert activitate is not None
        assert activitate.spatiu_id == ids['spatiu_a']
        assert activitate.zona_id == ids['zona_a']
        assert activitate.element_bim_id == ids['element_a']


def test_strict_user_fara_tenant_esueaza_inchis_la_creare(operator_client, app):
    ids = _creeaza_date(app)
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = operator_client.post('/activitati/adauga', data=_form_activitate(
        ids,
        TITLU_CREATE,
        bim_element_id=ids['element_a'],
    ))

    assert raspuns.status_code in (403, 404)
    _assert_activitate_nu_exista(app, TITLU_CREATE)


def test_bim_element_detaliu_exclude_activitati_si_pontaje_contaminate(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_admin_tenant(app, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    with _captured_templates(app) as templates:
        raspuns = authenticated_client.get(f'/bim/element/{ids["element_a"]}')

    assert raspuns.status_code == 200
    assert TITLU_A.encode() in raspuns.data
    assert TITLU_CONTAMINAT.encode() not in raspuns.data

    context = _context_template(templates, 'bim/element_detaliu.html')
    assert {r.activitate_principala for r in context['rapoarte']} == {TITLU_A}
    assert [p.proiect_id for p in context['pontaje']] == [ids['proiect_a']]


def test_bim_element_api_numara_doar_activitati_tenant_safe(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_admin_tenant(app, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.get(f'/bim/api/element/{ids["element_a"]}')

    assert raspuns.status_code == 200
    assert raspuns.get_json()['nr_activitati'] == 1


def _creeaza_date(app):
    from models import (
        Angajat, Cladire, ElementBIM, Nivel, Pontaj, Proiect,
        RaportActivitate, Santier, Spatiu, Tenant, Zona, db,
    )

    with app.app_context():
        tenant_a = Tenant(cod='test-ta-act-bim-route-a', nume='Tenant Act BIM Route A')
        tenant_b = Tenant(cod='test-ta-act-bim-route-b', nume='Tenant Act BIM Route B')
        db.session.add_all([tenant_a, tenant_b])
        db.session.commit()

        proiect_a = _proiect(tenant_a.id, 'TA-ACT-BIM-R-PRJ-A')
        proiect_b = _proiect(tenant_b.id, 'TA-ACT-BIM-R-PRJ-B')
        angajat_a = _angajat(tenant_a.id, 'TenantA', CNP_A)
        angajat_b = _angajat(tenant_b.id, 'TenantB', CNP_B)
        db.session.add_all([proiect_a, proiect_b, angajat_a, angajat_b])
        db.session.commit()

        site_a = Santier(tenant_id=tenant_a.id, proiect_id=proiect_a.id, cod='TA-ACT-BIM-R-SITE-A', nume='Site A')
        site_b = Santier(tenant_id=tenant_b.id, proiect_id=proiect_b.id, cod='TA-ACT-BIM-R-SITE-B', nume='Site B')
        db.session.add_all([site_a, site_b])
        db.session.commit()

        cladire_a = Cladire(santier_id=site_a.id, cod='TA-ACT-BIM-R-BLD-A', nume='Cladire A')
        cladire_b = Cladire(santier_id=site_b.id, cod='TA-ACT-BIM-R-BLD-B', nume='Cladire B')
        db.session.add_all([cladire_a, cladire_b])
        db.session.commit()

        nivel_a = Nivel(cladire_id=cladire_a.id, cod='TA-ACT-BIM-R-NIV-A', nume='Nivel A')
        nivel_b = Nivel(cladire_id=cladire_b.id, cod='TA-ACT-BIM-R-NIV-B', nume='Nivel B')
        db.session.add_all([nivel_a, nivel_b])
        db.session.commit()

        zona_a = Zona(cladire_id=cladire_a.id, nivel_id=nivel_a.id, cod='TA-ACT-BIM-R-ZON-A', nume='Zona A')
        zona_b = Zona(cladire_id=cladire_b.id, nivel_id=nivel_b.id, cod='TA-ACT-BIM-R-ZON-B', nume='Zona B')
        db.session.add_all([zona_a, zona_b])
        db.session.commit()

        spatiu_a = Spatiu(nivel_id=nivel_a.id, zona_id=zona_a.id, cod='TA-ACT-BIM-R-SP-A', nume='Spatiu A')
        spatiu_b = Spatiu(nivel_id=nivel_b.id, zona_id=zona_b.id, cod='TA-ACT-BIM-R-SP-B', nume='Spatiu B')
        db.session.add_all([spatiu_a, spatiu_b])
        db.session.commit()

        element_a = ElementBIM(
            cladire_id=cladire_a.id,
            nivel_id=nivel_a.id,
            spatiu_id=spatiu_a.id,
            cod='TA-ACT-BIM-R-EL-A',
            nume='Element A',
            tip_element='wall',
        )
        element_b = ElementBIM(
            cladire_id=cladire_b.id,
            nivel_id=nivel_b.id,
            spatiu_id=spatiu_b.id,
            cod='TA-ACT-BIM-R-EL-B',
            nume='Element B',
            tip_element='wall',
        )
        db.session.add_all([element_a, element_b])
        db.session.commit()

        activitate_a = RaportActivitate(
            angajat_id=angajat_a.id,
            proiect_id=proiect_a.id,
            element_bim_id=element_a.id,
            spatiu_id=spatiu_a.id,
            zona_id=zona_a.id,
            data=date(2026, 3, 14),
            activitate_principala=TITLU_A,
            tip_activitate='zilnica',
            status='trimis',
        )
        activitate_b = RaportActivitate(
            angajat_id=angajat_b.id,
            proiect_id=proiect_b.id,
            element_bim_id=element_b.id,
            spatiu_id=spatiu_b.id,
            zona_id=zona_b.id,
            data=date(2026, 3, 14),
            activitate_principala=TITLU_B,
            tip_activitate='zilnica',
            status='trimis',
        )
        activitate_contaminata = RaportActivitate(
            angajat_id=angajat_b.id,
            proiect_id=proiect_b.id,
            element_bim_id=element_a.id,
            spatiu_id=spatiu_a.id,
            zona_id=zona_a.id,
            data=date(2026, 3, 15),
            activitate_principala=TITLU_CONTAMINAT,
            tip_activitate='zilnica',
            status='trimis',
        )
        db.session.add_all([activitate_a, activitate_b, activitate_contaminata])
        db.session.commit()

        pontaj_a = Pontaj(
            angajat_id=angajat_a.id,
            proiect_id=proiect_a.id,
            element_bim_id=element_a.id,
            spatiu_id=spatiu_a.id,
            data=date(2026, 3, 14),
            ore_lucrate=8,
        )
        pontaj_contaminat = Pontaj(
            angajat_id=angajat_b.id,
            proiect_id=proiect_b.id,
            element_bim_id=element_a.id,
            spatiu_id=spatiu_a.id,
            data=date(2026, 3, 15),
            ore_lucrate=8,
        )
        db.session.add_all([pontaj_a, pontaj_contaminat])
        db.session.commit()

        return {
            'tenant_a': tenant_a.id,
            'tenant_b': tenant_b.id,
            'proiect_a': proiect_a.id,
            'proiect_b': proiect_b.id,
            'angajat_a': angajat_a.id,
            'angajat_b': angajat_b.id,
            'site_a': site_a.id,
            'site_b': site_b.id,
            'cladire_a': cladire_a.id,
            'cladire_b': cladire_b.id,
            'nivel_a': nivel_a.id,
            'nivel_b': nivel_b.id,
            'zona_a': zona_a.id,
            'zona_b': zona_b.id,
            'spatiu_a': spatiu_a.id,
            'spatiu_b': spatiu_b.id,
            'element_a': element_a.id,
            'element_b': element_b.id,
        }


def _proiect(tenant_id, cod):
    from models import Proiect

    return Proiect(
        tenant_id=tenant_id,
        cod_proiect=cod,
        nume=cod,
        data_start=date(2026, 1, 1),
        status='activ',
    )


def _angajat(tenant_id, nume, cnp):
    from models import Angajat

    return Angajat(
        tenant_id=tenant_id,
        nume=nume,
        prenume='ActivityBIM',
        cnp=cnp,
        functie='Inginer',
        data_angajare=date(2026, 1, 1),
        status='activ',
    )


def _form_activitate(ids, titlu, **extra):
    data = {
        'angajat_id': str(ids['angajat_a']),
        'proiect_ids[]': [str(ids['proiect_a'])],
        'data': '2026-03-16',
        'tip_activitate': 'zilnica',
        'activitate_principala': titlu,
        'status_executie': 'planificata',
        'actiune': 'draft',
    }
    for key, value in extra.items():
        data[key] = str(value)
    return data


def _assert_activitate_nu_exista(app, titlu):
    with app.app_context():
        from models import RaportActivitate

        assert RaportActivitate.query.filter_by(activitate_principala=titlu).first() is None


def _seteaza_admin_tenant(app, tenant_id):
    from models import Utilizator, db

    with app.app_context():
        user = Utilizator.query.filter_by(email='admin_test@test.local').first()
        user.tenant_id = tenant_id
        db.session.commit()


@contextmanager
def _captured_templates(app):
    recorded = []

    def record(sender, template, context, **extra):
        recorded.append((template, context))

    template_rendered.connect(record, app)
    try:
        yield recorded
    finally:
        template_rendered.disconnect(record, app)


def _context_template(templates, nume):
    for template, context in templates:
        if template.name == nume:
            return context
    raise AssertionError(f'Template {nume} nu a fost randat.')


def _curata_date(app):
    from models import (
        Angajat, Cladire, ElementBIM, Nivel, Pontaj, Proiect,
        RaportActivitate, Santier, Spatiu, Tenant, Utilizator, Zona, db,
    )

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
                TITLU_CONTAMINAT,
                TITLU_CREATE,
            ])
        ).delete(synchronize_session=False)
        proiecte_test = Proiect.query.filter(
            Proiect.cod_proiect.like('TA-ACT-BIM-R-%')
        ).with_entities(Proiect.id)
        for pontaj in Pontaj.query.filter(Pontaj.proiect_id.in_(proiecte_test)).all():
            db.session.delete(pontaj)

        for cls in (ElementBIM, Spatiu, Zona, Nivel, Cladire, Santier):
            for obj in cls.query.filter(cls.cod.like('TA-ACT-BIM-R-%')).all():
                db.session.delete(obj)
        Proiect.query.filter(Proiect.cod_proiect.like('TA-ACT-BIM-R-%')).delete(synchronize_session=False)
        Angajat.query.filter(Angajat.cnp.in_([CNP_A, CNP_B])).delete(synchronize_session=False)
        Tenant.query.filter(Tenant.cod.like('test-ta-act-bim-route-%')).delete(synchronize_session=False)
        db.session.commit()
