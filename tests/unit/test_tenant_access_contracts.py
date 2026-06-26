"""Teste pentru helper-ele tenant-safe din domeniul contracte."""

from datetime import date

import pytest
from flask import g
from werkzeug.exceptions import HTTPException


@pytest.fixture(autouse=True)
def curata_tenant_access_contracts(app):
    _curata_date(app)
    yield
    _curata_date(app)


def test_query_contracts_for_tenant_strict_returneaza_doar_tenantul(app):
    from services.security.tenant_access import query_contracts_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        contracte = query_contracts_for_tenant().filter_by(
            nr_contract='TA-HELPER-A'
        ).all()
        straine = query_contracts_for_tenant().filter_by(
            nr_contract='TA-HELPER-B'
        ).all()

    assert len(contracte) == 1
    assert straine == []


def test_get_contract_or_404_blocheaza_contract_strain(app):
    from services.security.tenant_access import get_contract_or_404

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        with pytest.raises(HTTPException) as exc:
            get_contract_or_404(ids['contract_b'])

    assert exc.value.code == 404


def test_require_contract_inputs_same_tenant_blocheaza_proiect_strain(app):
    from services.security.tenant_access import require_contract_inputs_same_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        with pytest.raises(HTTPException) as exc:
            require_contract_inputs_same_tenant(
                proiect_id=ids['proiect_b'],
                contract_id=ids['contract_a'],
            )

    assert exc.value.code == 404


def test_query_tarife_categorie_strict_include_global_exclude_strain(app):
    from models import TarifCategorie
    from services.security.tenant_access import query_tarife_categorie_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        tarife = query_tarife_categorie_for_tenant(
            include_global_defaults=True
        ).filter(
            TarifCategorie.categorie_lucrare.like('ta-helper-%')
        ).all()

    categorii = {t.categorie_lucrare for t in tarife}
    assert 'ta-helper-global' in categorii
    assert 'ta-helper-a' in categorii
    assert 'ta-helper-b' not in categorii


def test_query_tarife_categorie_strict_default_nu_include_global(app):
    from models import TarifCategorie
    from services.security.tenant_access import query_tarife_categorie_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        tarife = query_tarife_categorie_for_tenant().filter(
            TarifCategorie.categorie_lucrare.like('ta-helper-%')
        ).all()

    categorii = {t.categorie_lucrare for t in tarife}
    assert categorii == {'ta-helper-a'}


def _creeaza_date(app):
    from models import db, Contract, Proiect, TarifCategorie, Tenant

    with app.app_context():
        tenant_a = Tenant(cod='test-ta-helper-a', nume='Tenant Helper A')
        tenant_b = Tenant(cod='test-ta-helper-b', nume='Tenant Helper B')
        db.session.add_all([tenant_a, tenant_b])
        db.session.commit()

        proiect_a = Proiect(
            tenant_id=tenant_a.id,
            cod_proiect='TA-HELPER-PRJ-A',
            nume='Tenant Helper Project A',
            data_start=date(2026, 1, 1),
            status='activ',
        )
        proiect_b = Proiect(
            tenant_id=tenant_b.id,
            cod_proiect='TA-HELPER-PRJ-B',
            nume='Tenant Helper Project B',
            data_start=date(2026, 1, 1),
            status='activ',
        )
        db.session.add_all([proiect_a, proiect_b])
        db.session.commit()

        contract_a = Contract(
            tenant_id=tenant_a.id,
            proiect_id=proiect_a.id,
            nr_contract='TA-HELPER-A',
            data_semnare=date(2026, 1, 1),
            status='activ',
        )
        contract_b = Contract(
            tenant_id=tenant_b.id,
            proiect_id=proiect_b.id,
            nr_contract='TA-HELPER-B',
            data_semnare=date(2026, 1, 1),
            status='activ',
        )
        db.session.add_all([contract_a, contract_b])
        db.session.commit()

        tarif_global = TarifCategorie(
            tenant_id=None,
            proiect_id=None,
            disciplina='general',
            categorie_lucrare='ta-helper-global',
            tarif_baza=100,
        )
        tarif_a = TarifCategorie(
            tenant_id=tenant_a.id,
            proiect_id=None,
            disciplina='general',
            categorie_lucrare='ta-helper-a',
            tarif_baza=200,
        )
        tarif_b = TarifCategorie(
            tenant_id=tenant_b.id,
            proiect_id=None,
            disciplina='general',
            categorie_lucrare='ta-helper-b',
            tarif_baza=300,
        )
        db.session.add_all([tarif_global, tarif_a, tarif_b])
        db.session.commit()

        return {
            'tenant_a': tenant_a.id,
            'tenant_b': tenant_b.id,
            'proiect_a': proiect_a.id,
            'proiect_b': proiect_b.id,
            'contract_a': contract_a.id,
            'contract_b': contract_b.id,
        }


def _curata_date(app):
    from models import db, Contract, Proiect, TarifCategorie, Tenant

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'

        TarifCategorie.query.filter(
            TarifCategorie.categorie_lucrare.like('ta-helper-%')
        ).delete(synchronize_session=False)
        Contract.query.filter(Contract.nr_contract.like('TA-HELPER-%')).delete()
        Proiect.query.filter(Proiect.cod_proiect.like('TA-HELPER-PRJ-%')).delete()
        Tenant.query.filter(Tenant.cod.like('test-ta-helper-%')).delete()
        db.session.commit()
