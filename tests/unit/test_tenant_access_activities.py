"""Teste pentru helperii tenant-safe RaportActivitate."""

from datetime import date

import pytest
from flask import g
from werkzeug.exceptions import HTTPException


TITLU_A = 'TA_ACT_HELPER_A'
TITLU_B = 'TA_ACT_HELPER_B'


@pytest.fixture(autouse=True)
def curata_activity_helpers(app):
    _curata_date(app)
    yield
    _curata_date(app)


def test_query_activities_for_tenant_returneaza_doar_tenantul_curent(app):
    from models import RaportActivitate
    from services.security.tenant_access import query_activities_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        titluri = {
            a.activitate_principala
            for a in query_activities_for_tenant().filter(
                RaportActivitate.activitate_principala.in_([TITLU_A, TITLU_B])
            ).all()
        }

    assert titluri == {TITLU_A}


def test_get_activity_or_404_returneaza_activitate_acelasi_tenant(app):
    from services.security.tenant_access import get_activity_or_404

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        activitate = get_activity_or_404(ids['activitate_a'])

    assert activitate.activitate_principala == TITLU_A


def test_get_activity_or_404_blocheaza_activitate_straina(app):
    from services.security.tenant_access import get_activity_or_404

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        with pytest.raises(HTTPException) as exc:
            get_activity_or_404(ids['activitate_b'])

    assert exc.value.code == 404


def test_ensure_activity_same_tenant_valideaza_si_respinge(app):
    from models import RaportActivitate
    from services.security.tenant_access import (
        TenantAccessDenied,
        ensure_activity_same_tenant,
        require_activity_same_tenant,
    )

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        activitate_a = RaportActivitate.query.get(ids['activitate_a'])
        activitate_b = RaportActivitate.query.get(ids['activitate_b'])

        assert ensure_activity_same_tenant(activitate_a) is activitate_a
        with pytest.raises(TenantAccessDenied):
            ensure_activity_same_tenant(activitate_b)
        with pytest.raises(HTTPException) as exc:
            require_activity_same_tenant(activitate_b)

    assert exc.value.code == 404


def test_optional_fara_tenant_pastreaza_comportament_migrare(app):
    from models import RaportActivitate
    from services.security.tenant_access import query_activities_for_tenant

    _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'optional'

        titluri = {
            a.activitate_principala
            for a in query_activities_for_tenant().filter(
                RaportActivitate.activitate_principala.in_([TITLU_A, TITLU_B])
            ).all()
        }

    assert titluri == {TITLU_A, TITLU_B}


def _creeaza_date(app):
    from models import db, Angajat, Proiect, RaportActivitate, Tenant

    with app.app_context():
        tenant_a = Tenant(cod='test-ta-act-helper-a', nume='Tenant Act Helper A')
        tenant_b = Tenant(cod='test-ta-act-helper-b', nume='Tenant Act Helper B')
        db.session.add_all([tenant_a, tenant_b])
        db.session.commit()

        proiect_a = Proiect(
            tenant_id=tenant_a.id,
            cod_proiect='TA-ACT-H-P-A',
            nume='Tenant Act Helper Project A',
            data_start=date(2026, 1, 1),
            status='activ',
        )
        proiect_b = Proiect(
            tenant_id=tenant_b.id,
            cod_proiect='TA-ACT-H-P-B',
            nume='Tenant Act Helper Project B',
            data_start=date(2026, 1, 1),
            status='activ',
        )
        angajat_a = Angajat(
            tenant_id=tenant_a.id,
            nume='TenantA',
            prenume='Activitate',
            cnp='7900101010101',
            functie='Inginer',
            data_angajare=date(2026, 1, 1),
            status='activ',
        )
        angajat_b = Angajat(
            tenant_id=tenant_b.id,
            nume='TenantB',
            prenume='Activitate',
            cnp='7900101010102',
            functie='Inginer',
            data_angajare=date(2026, 1, 1),
            status='activ',
        )
        db.session.add_all([proiect_a, proiect_b, angajat_a, angajat_b])
        db.session.commit()

        activitate_a = RaportActivitate(
            angajat_id=angajat_a.id,
            proiect_id=proiect_a.id,
            data=date(2026, 1, 2),
            activitate_principala=TITLU_A,
            tip_activitate='zilnica',
            status='trimis',
        )
        activitate_b = RaportActivitate(
            angajat_id=angajat_b.id,
            proiect_id=proiect_b.id,
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
            'activitate_a': activitate_a.id,
            'activitate_b': activitate_b.id,
        }


def _curata_date(app):
    from models import db, Angajat, Proiect, RaportActivitate, Tenant

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        RaportActivitate.query.filter(
            RaportActivitate.activitate_principala.in_([TITLU_A, TITLU_B])
        ).delete(synchronize_session=False)
        Proiect.query.filter(Proiect.cod_proiect.like('TA-ACT-H-%')).delete(synchronize_session=False)
        Angajat.query.filter(Angajat.cnp.in_(['7900101010101', '7900101010102'])).delete(synchronize_session=False)
        Tenant.query.filter(Tenant.cod.like('test-ta-act-helper-%')).delete(synchronize_session=False)
        db.session.commit()

