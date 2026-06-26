"""Teste pentru helperii tenant-safe Pontaj."""

from datetime import date

import pytest
from flask import g
from werkzeug.exceptions import HTTPException


CNP_A = '7900303010101'
CNP_B = '7900303010102'
COD_PROIECT_A = 'TA-PONT-H-P-A'
COD_PROIECT_B = 'TA-PONT-H-P-B'


@pytest.fixture(autouse=True)
def curata_timesheet_helpers(app):
    _curata_date(app)
    yield
    _curata_date(app)


def test_query_timesheets_for_tenant_returneaza_doar_tenantul_curent(app):
    from models import Pontaj
    from services.security.tenant_access import query_timesheets_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        pontaje_ids = {
            p.id
            for p in query_timesheets_for_tenant().filter(
                Pontaj.id.in_([ids['pontaj_a'], ids['pontaj_b']])
            ).all()
        }

    assert pontaje_ids == {ids['pontaj_a']}


def test_get_timesheet_or_404_returneaza_pontaj_acelasi_tenant(app):
    from services.security.tenant_access import get_timesheet_or_404

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        pontaj = get_timesheet_or_404(ids['pontaj_a'])

    assert pontaj.id == ids['pontaj_a']


def test_get_timesheet_or_404_blocheaza_pontaj_strain(app):
    from services.security.tenant_access import get_timesheet_or_404

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        with pytest.raises(HTTPException) as exc:
            get_timesheet_or_404(ids['pontaj_b'])

    assert exc.value.code == 404


def test_ensure_timesheet_same_tenant_valideaza_si_respinge(app):
    from models import Pontaj
    from services.security.tenant_access import (
        TenantAccessDenied,
        ensure_timesheet_same_tenant,
        require_timesheet_same_tenant,
    )

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        pontaj_a = Pontaj.query.get(ids['pontaj_a'])
        pontaj_b = Pontaj.query.get(ids['pontaj_b'])

        assert ensure_timesheet_same_tenant(pontaj_a) is pontaj_a
        with pytest.raises(TenantAccessDenied):
            ensure_timesheet_same_tenant(pontaj_b)
        with pytest.raises(HTTPException) as exc:
            require_timesheet_same_tenant(pontaj_b)

    assert exc.value.code == 404


def test_ensure_timesheet_inputs_same_tenant_blocheaza_input_strain(app):
    from services.security.tenant_access import (
        TenantAccessDenied,
        ensure_timesheet_inputs_same_tenant,
    )

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        assert ensure_timesheet_inputs_same_tenant(
            proiect_id=ids['proiect_a'],
            angajat_id=ids['angajat_a'],
        )
        with pytest.raises(TenantAccessDenied):
            ensure_timesheet_inputs_same_tenant(
                proiect_id=ids['proiect_b'],
                angajat_id=ids['angajat_a'],
            )
        with pytest.raises(TenantAccessDenied):
            ensure_timesheet_inputs_same_tenant(
                proiect_id=ids['proiect_a'],
                angajat_id=ids['angajat_b'],
            )


def test_optional_fara_tenant_pastreaza_comportament_migrare(app):
    from models import Pontaj
    from services.security.tenant_access import query_timesheets_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'optional'

        pontaje_ids = {
            p.id
            for p in query_timesheets_for_tenant().filter(
                Pontaj.id.in_([ids['pontaj_a'], ids['pontaj_b']])
            ).all()
        }

    assert pontaje_ids == {ids['pontaj_a'], ids['pontaj_b']}


def _creeaza_date(app):
    from models import db, Angajat, Pontaj, Proiect, Tenant

    with app.app_context():
        tenant_a = Tenant(cod='test-ta-pont-helper-a', nume='Tenant Pont Helper A')
        tenant_b = Tenant(cod='test-ta-pont-helper-b', nume='Tenant Pont Helper B')
        db.session.add_all([tenant_a, tenant_b])
        db.session.commit()

        proiect_a = Proiect(
            tenant_id=tenant_a.id,
            cod_proiect=COD_PROIECT_A,
            nume='Tenant Pont Helper Project A',
            data_start=date(2026, 1, 1),
            status='activ',
        )
        proiect_b = Proiect(
            tenant_id=tenant_b.id,
            cod_proiect=COD_PROIECT_B,
            nume='Tenant Pont Helper Project B',
            data_start=date(2026, 1, 1),
            status='activ',
        )
        angajat_a = Angajat(
            tenant_id=tenant_a.id,
            nume='TenantA',
            prenume='Pontaj',
            cnp=CNP_A,
            functie='Inginer',
            data_angajare=date(2026, 1, 1),
            status='activ',
        )
        angajat_b = Angajat(
            tenant_id=tenant_b.id,
            nume='TenantB',
            prenume='Pontaj',
            cnp=CNP_B,
            functie='Inginer',
            data_angajare=date(2026, 1, 1),
            status='activ',
        )
        db.session.add_all([proiect_a, proiect_b, angajat_a, angajat_b])
        db.session.commit()

        pontaj_a = Pontaj(
            angajat_id=angajat_a.id,
            proiect_id=proiect_a.id,
            data=date(2026, 2, 2),
            ore_lucrate=8,
            ore_normale=8,
            status='trimis',
        )
        pontaj_b = Pontaj(
            angajat_id=angajat_b.id,
            proiect_id=proiect_b.id,
            data=date(2026, 2, 2),
            ore_lucrate=8,
            ore_normale=8,
            status='trimis',
        )
        db.session.add_all([pontaj_a, pontaj_b])
        db.session.commit()

        return {
            'tenant_a': tenant_a.id,
            'tenant_b': tenant_b.id,
            'proiect_a': proiect_a.id,
            'proiect_b': proiect_b.id,
            'angajat_a': angajat_a.id,
            'angajat_b': angajat_b.id,
            'pontaj_a': pontaj_a.id,
            'pontaj_b': pontaj_b.id,
        }


def _curata_date(app):
    from models import db, Angajat, Pontaj, Proiect, Tenant

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        Pontaj.query.filter(Pontaj.data.in_([
            date(2026, 2, 2),
        ])).delete(synchronize_session=False)
        Proiect.query.filter(Proiect.cod_proiect.like('TA-PONT-H-%')).delete(synchronize_session=False)
        Angajat.query.filter(Angajat.cnp.in_([CNP_A, CNP_B])).delete(synchronize_session=False)
        Tenant.query.filter(Tenant.cod.like('test-ta-pont-helper-%')).delete(synchronize_session=False)
        db.session.commit()
