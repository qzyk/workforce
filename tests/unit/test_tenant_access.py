"""Teste pentru services.security.tenant_access."""

from datetime import date

import pytest
from flask import g
from flask_login import login_user
from werkzeug.exceptions import HTTPException


CODURI_PROIECTE = ('TA-P1', 'TA-P2', 'TA-GLOBAL')


@pytest.fixture(autouse=True)
def curata_tenant_access(app):
    _curata_date(app)
    yield
    _curata_date(app)


def test_query_for_tenant_off_returneaza_nefiltrat(app):
    from models import Proiect
    from services.security.tenant_access import query_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'off'
        g.tenant_override = ids['tenant_1']

        coduri = _coduri(query_for_tenant(Proiect).filter(Proiect.cod_proiect.in_(CODURI_PROIECTE)).all())

    assert coduri == set(CODURI_PROIECTE)


def test_query_for_tenant_strict_returneaza_doar_tenantul_curent(app):
    from models import Proiect
    from services.security.tenant_access import query_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_1']

        coduri = _coduri(query_for_tenant(Proiect).filter(Proiect.cod_proiect.in_(CODURI_PROIECTE)).all())

    assert coduri == {'TA-P1'}


def test_query_for_tenant_strict_exclude_global_implicit(app):
    from models import Proiect
    from services.security.tenant_access import query_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_1']

        coduri = _coduri(query_for_tenant(Proiect).filter(Proiect.cod_proiect.in_(CODURI_PROIECTE)).all())

    assert 'TA-GLOBAL' not in coduri


def test_query_for_tenant_strict_include_global_explicit(app):
    from models import Proiect
    from services.security.tenant_access import query_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_1']

        coduri = _coduri(
            query_for_tenant(Proiect, include_global=True)
            .filter(Proiect.cod_proiect.in_(CODURI_PROIECTE))
            .all()
        )

    assert coduri == {'TA-P1', 'TA-GLOBAL'}


def test_get_or_404_for_tenant_returneaza_obiect_acelasi_tenant(app):
    from models import Proiect
    from services.security.tenant_access import get_or_404_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_1']

        proiect = get_or_404_for_tenant(Proiect, ids['proiect_1'])

    assert proiect.cod_proiect == 'TA-P1'


def test_get_or_404_for_tenant_blocheaza_obiect_strain(app):
    from models import Proiect
    from services.security.tenant_access import get_or_404_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_1']

        with pytest.raises(HTTPException) as exc:
            get_or_404_for_tenant(Proiect, ids['proiect_2'])

    assert exc.value.code == 404


def test_user_normal_fara_tenant_in_strict_nu_vede_randuri_tenant(app):
    from models import Proiect, Utilizator
    from services.security.tenant_access import query_for_tenant

    _creeaza_date(app)
    user_id = _creeaza_utilizator(app, email='tenant_access_operator@test.local', rol='operator')

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        login_user(Utilizator.query.get(user_id))

        rezultate = query_for_tenant(Proiect).filter(Proiect.cod_proiect.in_(CODURI_PROIECTE)).all()

    assert rezultate == []


def test_super_admin_in_strict_are_comportament_explicit_nefiltrat(app):
    from models import Proiect, Utilizator
    from services.security.tenant_access import query_for_tenant

    _creeaza_date(app)
    user_id = _creeaza_utilizator(app, email='tenant_access_admin@test.local', rol='admin')

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        login_user(Utilizator.query.get(user_id))

        coduri = _coduri(query_for_tenant(Proiect).filter(Proiect.cod_proiect.in_(CODURI_PROIECTE)).all())

    assert coduri == set(CODURI_PROIECTE)


def test_model_indirect_fara_tenant_id_ridica_unsupported(app):
    from models import AngajatProiect
    from services.security.tenant_access import TenantScopeUnsupported, query_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_1']

        with pytest.raises(TenantScopeUnsupported):
            query_for_tenant(AngajatProiect).all()


def _creeaza_date(app):
    from models import db, Proiect, Tenant

    with app.app_context():
        tenant_1 = Tenant(cod='test-ta-1', nume='Tenant Access 1')
        tenant_2 = Tenant(cod='test-ta-2', nume='Tenant Access 2')
        db.session.add_all([tenant_1, tenant_2])
        db.session.commit()

        proiect_1 = Proiect(
            tenant_id=tenant_1.id,
            cod_proiect='TA-P1',
            nume='Tenant Access P1',
            data_start=date(2026, 1, 1),
            status='activ',
        )
        proiect_2 = Proiect(
            tenant_id=tenant_2.id,
            cod_proiect='TA-P2',
            nume='Tenant Access P2',
            data_start=date(2026, 1, 1),
            status='activ',
        )
        proiect_global = Proiect(
            tenant_id=None,
            cod_proiect='TA-GLOBAL',
            nume='Tenant Access Global',
            data_start=date(2026, 1, 1),
            status='activ',
        )
        db.session.add_all([proiect_1, proiect_2, proiect_global])
        db.session.commit()

        return {
            'tenant_1': tenant_1.id,
            'tenant_2': tenant_2.id,
            'proiect_1': proiect_1.id,
            'proiect_2': proiect_2.id,
            'proiect_global': proiect_global.id,
        }


def _creeaza_utilizator(app, email, rol):
    from models import db, Utilizator

    with app.app_context():
        user = Utilizator(
            nume='Tenant',
            prenume='Access',
            email=email,
            rol=rol,
            activ=True,
            tenant_id=None,
        )
        user.set_password('tenant_access_test')
        db.session.add(user)
        db.session.commit()
        return user.id


def _curata_date(app):
    from models import db, Proiect, Tenant, Utilizator

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'

        for user in Utilizator.query.filter(Utilizator.email.in_([
            'admin_test@test.local',
            'operator_test@test.local',
        ])).all():
            user.tenant_id = None

        for proiect in Proiect.query.filter(Proiect.cod_proiect.in_(CODURI_PROIECTE)).all():
            db.session.delete(proiect)

        for user in Utilizator.query.filter(Utilizator.email.like('tenant_access_%@test.local')).all():
            db.session.delete(user)

        for tenant in Tenant.query.filter(Tenant.cod.like('test-ta-%')).all():
            db.session.delete(tenant)

        db.session.commit()


def _coduri(proiecte):
    return {proiect.cod_proiect for proiect in proiecte}

