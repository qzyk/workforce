"""Teste pentru helper-ele tenant-safe din reporting/dashboard."""

import json
from datetime import date

import pytest
from flask import g
from werkzeug.exceptions import HTTPException


@pytest.fixture(autouse=True)
def curata_tenant_access_reporting(app):
    _curata_date(app)
    yield
    _curata_date(app)


def test_query_reports_strict_returneaza_doar_rapoartele_tenantului(app):
    from models import Raport
    from services.security.tenant_access import query_reports_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        titluri = {
            r.titlu for r in query_reports_for_tenant()
            .filter(Raport.titlu.like('TA-REPORT-HELPER-%'))
            .all()
        }

    assert titluri == {'TA-REPORT-HELPER-A', 'TA-REPORT-HELPER-PROJECT-A'}


def test_get_report_or_404_blocheaza_raport_strain(app):
    from services.security.tenant_access import get_report_or_404

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        with pytest.raises(HTTPException) as exc:
            get_report_or_404(ids['raport_b'])

    assert exc.value.code == 404


def test_report_parametru_proiect_are_prioritate_fata_de_generator(app):
    from services.security.tenant_access import get_report_or_404

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        with pytest.raises(HTTPException) as exc:
            get_report_or_404(ids['raport_generator_a_proiect_b'])

    assert exc.value.code == 404


def test_report_cu_proiect_salvat_si_fara_generator_este_acceptat(app):
    from services.security.tenant_access import get_report_or_404

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        raport = get_report_or_404(ids['raport_owner_proiect_a'])

    assert raport.titlu == 'TA-REPORT-HELPER-PROJECT-A'


def test_report_ambiguu_fara_owner_esueaza_in_strict(app):
    from services.security.tenant_access import get_report_or_404

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        with pytest.raises(HTTPException) as exc:
            get_report_or_404(ids['raport_ownerless'])

    assert exc.value.code == 404


def test_reporting_project_scope_blocheaza_proiect_strain(app):
    from services.security.tenant_access import (
        TenantAccessDenied,
        ensure_reporting_project_scope,
    )

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        assert ensure_reporting_project_scope(ids['proiect_a']) is True
        with pytest.raises(TenantAccessDenied):
            ensure_reporting_project_scope(ids['proiect_b'])


def test_optional_fara_tenant_ramane_permisiv_pentru_istoric(app):
    from models import Raport
    from services.security.tenant_access import query_reports_for_tenant

    _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'optional'

        titluri = {
            r.titlu for r in query_reports_for_tenant()
            .filter(Raport.titlu.like('TA-REPORT-HELPER-%'))
            .all()
        }

    assert {'TA-REPORT-HELPER-A', 'TA-REPORT-HELPER-B'} <= titluri


def _creeaza_date(app):
    from models import Angajat, Proiect, Raport, Tenant, Utilizator, db

    with app.app_context():
        tenant_a = Tenant(cod='test-ta-report-helper-a', nume='Tenant Reporting Helper A')
        tenant_b = Tenant(cod='test-ta-report-helper-b', nume='Tenant Reporting Helper B')
        db.session.add_all([tenant_a, tenant_b])
        db.session.commit()

        user_a = _user(tenant_a.id, 'ta-report-helper-a@test.local')
        user_b = _user(tenant_b.id, 'ta-report-helper-b@test.local')
        proiect_a = _proiect(tenant_a.id, 'TA-REPORT-HELPER-PRJ-A')
        proiect_b = _proiect(tenant_b.id, 'TA-REPORT-HELPER-PRJ-B')
        angajat_a = _angajat(tenant_a.id, '6990101010101', 'ReportHelperA')
        db.session.add_all([user_a, user_b, proiect_a, proiect_b, angajat_a])
        db.session.commit()

        raport_a = _raport(
            'TA-REPORT-HELPER-A',
            user_a.id,
            {'proiect_id': proiect_a.id},
        )
        raport_b = _raport(
            'TA-REPORT-HELPER-B',
            user_b.id,
            {'proiect_id': proiect_b.id},
        )
        raport_generator_a_proiect_b = _raport(
            'TA-REPORT-HELPER-GEN-A-PROJ-B',
            user_a.id,
            {'proiect_id': proiect_b.id},
        )
        raport_owner_proiect_a = _raport(
            'TA-REPORT-HELPER-PROJECT-A',
            None,
            {'proiect_id': proiect_a.id},
        )
        raport_ownerless = _raport('TA-REPORT-HELPER-OWNERLESS', None, None)
        db.session.add_all([
            raport_a,
            raport_b,
            raport_generator_a_proiect_b,
            raport_owner_proiect_a,
            raport_ownerless,
        ])
        db.session.commit()

        return {
            'tenant_a': tenant_a.id,
            'tenant_b': tenant_b.id,
            'proiect_a': proiect_a.id,
            'proiect_b': proiect_b.id,
            'angajat_a': angajat_a.id,
            'raport_b': raport_b.id,
            'raport_generator_a_proiect_b': raport_generator_a_proiect_b.id,
            'raport_owner_proiect_a': raport_owner_proiect_a.id,
            'raport_ownerless': raport_ownerless.id,
        }


def _user(tenant_id, email):
    from models import Utilizator

    user = Utilizator(
        tenant_id=tenant_id,
        nume='Report',
        prenume='Helper',
        email=email,
        rol='manager',
        activ=True,
    )
    user.set_password('test_pass_123')
    return user


def _proiect(tenant_id, cod):
    from models import Proiect

    return Proiect(
        tenant_id=tenant_id,
        cod_proiect=cod,
        nume=cod,
        data_start=date(2026, 1, 1),
        status='activ',
    )


def _angajat(tenant_id, cnp, nume):
    from models import Angajat

    return Angajat(
        tenant_id=tenant_id,
        nume=nume,
        prenume='Test',
        cnp=cnp,
        functie='Muncitor',
        data_angajare=date(2026, 1, 1),
        status='activ',
    )


def _raport(titlu, generat_de, params):
    from models import Raport

    return Raport(
        tip_raport='situatie_proiect',
        titlu=titlu,
        parametri=json.dumps(params) if params else None,
        fisier_path='/tmp/ta-report-helper.xlsx',
        format='xlsx',
        generat_de=generat_de,
        dimensiune_fisier=1,
    )


def _curata_date(app):
    from models import Angajat, Proiect, Raport, Tenant, Utilizator, db

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        Raport.query.filter(
            Raport.titlu.like('TA-REPORT-HELPER-%')
        ).delete(synchronize_session=False)
        Angajat.query.filter(
            Angajat.cnp.in_(['6990101010101'])
        ).delete(synchronize_session=False)
        Proiect.query.filter(
            Proiect.cod_proiect.like('TA-REPORT-HELPER-PRJ-%')
        ).delete(synchronize_session=False)
        Utilizator.query.filter(
            Utilizator.email.like('ta-report-helper-%')
        ).delete(synchronize_session=False)
        Tenant.query.filter(
            Tenant.cod.like('test-ta-report-helper-%')
        ).delete(synchronize_session=False)
        db.session.commit()
