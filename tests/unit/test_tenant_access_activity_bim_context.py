"""Teste pentru helperii tenant-safe ai contextului BIM din activitati."""

from datetime import date

import pytest
from werkzeug.exceptions import HTTPException

from services.security.tenant_access import TenantAccessDenied


@pytest.fixture(autouse=True)
def curata_activity_bim_context(app):
    _curata_date(app)
    yield
    _curata_date(app)


def test_context_bim_accepta_id_uri_acelasi_tenant(app):
    from services.security.tenant_access import ensure_activity_bim_context_same_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        context = ensure_activity_bim_context_same_tenant(
            santier_id=ids['site_a'],
            cladire_id=ids['cladire_a'],
            nivel_id=ids['nivel_a'],
            zona_id=ids['zona_a'],
            spatiu_id=ids['spatiu_a'],
            element_bim_id=ids['element_a'],
            proiect_id=ids['proiect_a'],
            tenant_id=ids['tenant_a'],
        )

    assert context['santier'].id == ids['site_a']
    assert context['spatiu'].id == ids['spatiu_a']
    assert context['element_bim'].id == ids['element_a']


def test_context_bim_blocheaza_element_strain(app):
    from services.security.tenant_access import ensure_activity_bim_context_same_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with pytest.raises(TenantAccessDenied):
            ensure_activity_bim_context_same_tenant(
                element_bim_id=ids['element_b'],
                proiect_id=ids['proiect_a'],
                tenant_id=ids['tenant_a'],
            )


def test_context_bim_blocheaza_spatiu_strain(app):
    from services.security.tenant_access import ensure_activity_bim_context_same_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with pytest.raises(TenantAccessDenied):
            ensure_activity_bim_context_same_tenant(
                spatiu_id=ids['spatiu_b'],
                proiect_id=ids['proiect_a'],
                tenant_id=ids['tenant_a'],
            )


def test_context_bim_blocheaza_mix_tenant(app):
    from services.security.tenant_access import require_activity_bim_context_same_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with pytest.raises(HTTPException) as exc:
            require_activity_bim_context_same_tenant(
                santier_id=ids['site_a'],
                element_bim_id=ids['element_b'],
                proiect_id=ids['proiect_a'],
                tenant_id=ids['tenant_a'],
            )

    assert exc.value.code == 404


def test_context_bim_off_mode_pastreaza_lookup_legacy(app):
    from services.security.tenant_access import ensure_activity_bim_context_same_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'off'
        context = ensure_activity_bim_context_same_tenant(
            element_bim_id=ids['element_b'],
            spatiu_id=ids['spatiu_b'],
            proiect_id=ids['proiect_b'],
            tenant_id=ids['tenant_a'],
        )

    assert context['element_bim'].id == ids['element_b']
    assert context['spatiu'].id == ids['spatiu_b']


def test_context_bim_strict_fara_tenant_esueaza_inchis(app):
    from services.security.tenant_access import ensure_activity_bim_context_same_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with pytest.raises(TenantAccessDenied):
            ensure_activity_bim_context_same_tenant(
                element_bim_id=ids['element_a'],
                proiect_id=ids['proiect_a'],
            )


def _creeaza_date(app):
    from models import (
        Cladire, ElementBIM, Nivel, Proiect, Santier, Spatiu, Tenant, Zona, db,
    )

    with app.app_context():
        tenant_a = Tenant(cod='test-ta-act-bim-unit-a', nume='Tenant Act BIM Unit A')
        tenant_b = Tenant(cod='test-ta-act-bim-unit-b', nume='Tenant Act BIM Unit B')
        db.session.add_all([tenant_a, tenant_b])
        db.session.commit()

        proiect_a = _proiect(tenant_a.id, 'TA-ACT-BIM-U-PRJ-A')
        proiect_b = _proiect(tenant_b.id, 'TA-ACT-BIM-U-PRJ-B')
        db.session.add_all([proiect_a, proiect_b])
        db.session.commit()

        site_a = Santier(tenant_id=tenant_a.id, proiect_id=proiect_a.id, cod='TA-ACT-BIM-U-SITE-A', nume='Site A')
        site_b = Santier(tenant_id=tenant_b.id, proiect_id=proiect_b.id, cod='TA-ACT-BIM-U-SITE-B', nume='Site B')
        db.session.add_all([site_a, site_b])
        db.session.commit()

        cladire_a = Cladire(santier_id=site_a.id, cod='TA-ACT-BIM-U-BLD-A', nume='Cladire A')
        cladire_b = Cladire(santier_id=site_b.id, cod='TA-ACT-BIM-U-BLD-B', nume='Cladire B')
        db.session.add_all([cladire_a, cladire_b])
        db.session.commit()

        nivel_a = Nivel(cladire_id=cladire_a.id, cod='TA-ACT-BIM-U-NIV-A', nume='Nivel A')
        nivel_b = Nivel(cladire_id=cladire_b.id, cod='TA-ACT-BIM-U-NIV-B', nume='Nivel B')
        db.session.add_all([nivel_a, nivel_b])
        db.session.commit()

        zona_a = Zona(cladire_id=cladire_a.id, nivel_id=nivel_a.id, cod='TA-ACT-BIM-U-ZON-A', nume='Zona A')
        zona_b = Zona(cladire_id=cladire_b.id, nivel_id=nivel_b.id, cod='TA-ACT-BIM-U-ZON-B', nume='Zona B')
        db.session.add_all([zona_a, zona_b])
        db.session.commit()

        spatiu_a = Spatiu(nivel_id=nivel_a.id, zona_id=zona_a.id, cod='TA-ACT-BIM-U-SP-A', nume='Spatiu A')
        spatiu_b = Spatiu(nivel_id=nivel_b.id, zona_id=zona_b.id, cod='TA-ACT-BIM-U-SP-B', nume='Spatiu B')
        db.session.add_all([spatiu_a, spatiu_b])
        db.session.commit()

        element_a = ElementBIM(
            cladire_id=cladire_a.id,
            nivel_id=nivel_a.id,
            spatiu_id=spatiu_a.id,
            cod='TA-ACT-BIM-U-EL-A',
            nume='Element A',
            tip_element='wall',
        )
        element_b = ElementBIM(
            cladire_id=cladire_b.id,
            nivel_id=nivel_b.id,
            spatiu_id=spatiu_b.id,
            cod='TA-ACT-BIM-U-EL-B',
            nume='Element B',
            tip_element='wall',
        )
        db.session.add_all([element_a, element_b])
        db.session.commit()

        return {
            'tenant_a': tenant_a.id,
            'tenant_b': tenant_b.id,
            'proiect_a': proiect_a.id,
            'proiect_b': proiect_b.id,
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


def _curata_date(app):
    from models import Cladire, ElementBIM, Nivel, Proiect, Santier, Spatiu, Tenant, Zona, db

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        for cls in (ElementBIM, Spatiu, Zona, Nivel, Cladire, Santier):
            for obj in cls.query.filter(cls.cod.like('TA-ACT-BIM-U-%')).all():
                db.session.delete(obj)
        for proiect in Proiect.query.filter(Proiect.cod_proiect.like('TA-ACT-BIM-U-%')).all():
            db.session.delete(proiect)
        for tenant in Tenant.query.filter(Tenant.cod.like('test-ta-act-bim-unit-%')).all():
            db.session.delete(tenant)
        db.session.commit()
