"""Teste pentru helper-ele tenant-safe BIM."""

from datetime import date

import pytest
from flask import g
from werkzeug.exceptions import HTTPException


@pytest.fixture(autouse=True)
def curata_tenant_access_bim(app):
    _curata_date(app)
    yield
    _curata_date(app)


def test_query_sites_models_issues_elements_strict_returneaza_doar_tenantul(app):
    from models import IssueBIM, ModelBIM, Santier
    from services.security.tenant_access import (
        query_bim_elements_for_tenant,
        query_bim_issues_for_tenant,
        query_bim_models_for_tenant,
        query_sites_for_tenant,
    )

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        santiere = query_sites_for_tenant().filter(
            Santier.cod.like('TA-BIM-%')
        ).all()
        modele = query_bim_models_for_tenant().filter(
            ModelBIM.nume.like('TA-BIM-%')
        ).all()
        elemente = query_bim_elements_for_tenant().all()
        issues = query_bim_issues_for_tenant().filter(
            IssueBIM.titlu.like('TA-BIM-%')
        ).all()

    assert {s.cod for s in santiere} == {'TA-BIM-SITE-A'}
    assert {m.nume for m in modele} == {'TA-BIM-MODEL-A'}
    assert {e.cod for e in elemente if e.cod.startswith('TA-BIM-')} == {'TA-BIM-EL-A'}
    assert {i.titlu for i in issues} == {'TA-BIM-ISSUE-A'}


def test_get_site_or_404_blocheaza_santier_strain(app):
    from services.security.tenant_access import get_site_or_404

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        with pytest.raises(HTTPException) as exc:
            get_site_or_404(ids['site_b'])

    assert exc.value.code == 404


def test_get_bim_model_or_404_blocheaza_model_strain(app):
    from services.security.tenant_access import get_bim_model_or_404

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        with pytest.raises(HTTPException) as exc:
            get_bim_model_or_404(ids['model_b'])

    assert exc.value.code == 404


def test_get_bim_model_version_or_404_blocheaza_versiune_straina(app):
    from services.security.tenant_access import get_bim_model_version_or_404

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        with pytest.raises(HTTPException) as exc:
            get_bim_model_version_or_404(ids['version_b'])

    assert exc.value.code == 404


def test_get_bim_element_or_404_blocheaza_element_strain(app):
    from services.security.tenant_access import get_bim_element_or_404

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        with pytest.raises(HTTPException) as exc:
            get_bim_element_or_404(ids['element_b'])

    assert exc.value.code == 404


def test_get_bim_issue_or_404_blocheaza_issue_strain(app):
    from services.security.tenant_access import get_bim_issue_or_404

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        with pytest.raises(HTTPException) as exc:
            get_bim_issue_or_404(ids['issue_b'])

    assert exc.value.code == 404


def test_optional_fara_tenant_ramane_permisiv_pentru_migrare(app):
    from models import Santier
    from services.security.tenant_access import query_sites_for_tenant

    _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'optional'

        coduri = {
            s.cod for s in query_sites_for_tenant()
            .filter(Santier.cod.like('TA-BIM-%'))
            .all()
        }

    assert coduri == {'TA-BIM-SITE-A', 'TA-BIM-SITE-B'}


def _creeaza_date(app):
    from models import (
        BIMModelVersion, Cladire, ElementBIM, IssueBIM, ModelBIM, Proiect,
        Santier, Tenant, db,
    )

    with app.app_context():
        tenant_a = Tenant(cod='test-ta-bim-a', nume='Tenant BIM A')
        tenant_b = Tenant(cod='test-ta-bim-b', nume='Tenant BIM B')
        db.session.add_all([tenant_a, tenant_b])
        db.session.commit()

        proiect_a = _proiect(tenant_a.id, 'TA-BIM-PRJ-A')
        proiect_b = _proiect(tenant_b.id, 'TA-BIM-PRJ-B')
        db.session.add_all([proiect_a, proiect_b])
        db.session.commit()

        site_a = Santier(
            tenant_id=tenant_a.id,
            proiect_id=proiect_a.id,
            cod='TA-BIM-SITE-A',
            nume='TA BIM Site A',
        )
        site_b = Santier(
            tenant_id=tenant_b.id,
            proiect_id=proiect_b.id,
            cod='TA-BIM-SITE-B',
            nume='TA BIM Site B',
        )
        db.session.add_all([site_a, site_b])
        db.session.commit()

        cladire_a = Cladire(santier_id=site_a.id, cod='TA-BIM-BLD-A', nume='A')
        cladire_b = Cladire(santier_id=site_b.id, cod='TA-BIM-BLD-B', nume='B')
        db.session.add_all([cladire_a, cladire_b])
        db.session.commit()

        model_a = ModelBIM(
            tenant_id=tenant_a.id,
            santier_id=site_a.id,
            cladire_id=cladire_a.id,
            nume='TA-BIM-MODEL-A',
            tip='ifc',
            fisier_path='/tmp/ta-bim-model-a.ifc',
        )
        model_b = ModelBIM(
            tenant_id=tenant_b.id,
            santier_id=site_b.id,
            cladire_id=cladire_b.id,
            nume='TA-BIM-MODEL-B',
            tip='ifc',
            fisier_path='/tmp/ta-bim-model-b.ifc',
        )
        db.session.add_all([model_a, model_b])
        db.session.commit()

        version_a = BIMModelVersion(
            tenant_id=tenant_a.id,
            model_id=model_a.id,
            versiune='A',
            status='published',
            fisier_path='/tmp/ta-bim-version-a.ifc',
        )
        version_b = BIMModelVersion(
            tenant_id=tenant_b.id,
            model_id=model_b.id,
            versiune='B',
            status='published',
            fisier_path='/tmp/ta-bim-version-b.ifc',
        )
        db.session.add_all([version_a, version_b])
        db.session.commit()

        element_a = ElementBIM(
            model_bim_id=model_a.id,
            cladire_id=cladire_a.id,
            cod='TA-BIM-EL-A',
            nume='Element A',
            tip_element='wall',
        )
        element_b = ElementBIM(
            model_bim_id=model_b.id,
            cladire_id=cladire_b.id,
            cod='TA-BIM-EL-B',
            nume='Element B',
            tip_element='wall',
        )
        db.session.add_all([element_a, element_b])
        db.session.commit()

        issue_a = IssueBIM(
            tenant_id=tenant_a.id,
            element_bim_id=element_a.id,
            cladire_id=cladire_a.id,
            titlu='TA-BIM-ISSUE-A',
            status='deschis',
        )
        issue_b = IssueBIM(
            tenant_id=tenant_b.id,
            element_bim_id=element_b.id,
            cladire_id=cladire_b.id,
            titlu='TA-BIM-ISSUE-B',
            status='deschis',
        )
        db.session.add_all([issue_a, issue_b])
        db.session.commit()

        return {
            'tenant_a': tenant_a.id,
            'tenant_b': tenant_b.id,
            'site_b': site_b.id,
            'model_b': model_b.id,
            'version_b': version_b.id,
            'element_b': element_b.id,
            'issue_b': issue_b.id,
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


def _curata_date(app):
    from models import (
        BIMModelVersion, Cladire, ElementBIM, IssueBIM, ModelBIM, Proiect,
        Santier, Tenant, db,
    )

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        for cls in (BIMModelVersion, IssueBIM, ElementBIM, ModelBIM, Cladire, Santier):
            for obj in cls.query.all():
                db.session.delete(obj)
        for proiect in Proiect.query.filter(Proiect.cod_proiect.like('TA-BIM-%')).all():
            db.session.delete(proiect)
        for tenant in Tenant.query.filter(Tenant.cod.like('test-ta-bim-%')).all():
            db.session.delete(tenant)
        db.session.commit()
