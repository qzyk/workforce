"""Teste directe pentru services/activity_service.py (S1.1A).

Verifica boundary-ul de serviciu pentru contextul de citire/formular al
activitatilor: scoping tenant pe panou si pe dropdown-urile de formular,
comportament pe moduri (off/strict) si fail-closed pentru user fara tenant.
"""

from datetime import date

import pytest


class _FakeUser:
    """Utilizator minimal pentru apelurile de context (read-only)."""

    def __init__(self, rol='manager', email=None, tenant_id=None):
        self.rol = rol
        self.email = email
        self.tenant_id = tenant_id
        self.is_authenticated = True
        self.is_admin = (rol == 'admin')


@pytest.fixture(autouse=True)
def curata_s11a(app):
    _curata(app)
    yield
    _curata(app)


def test_panel_context_doar_activitati_acelasi_tenant(app):
    from services.activity_service import get_activity_panel_context

    ids = _seed(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        ctx = get_activity_panel_context(
            filters={},
            current_user=_FakeUser(rol='manager'),
            tenant_id=ids['tenant_a'],
        )

    recente_ids = {a.id for a in ctx['activitati_recente']}
    assert ids['act_a'] in recente_ids
    assert ids['act_b'] not in recente_ids


def test_form_context_doar_proiecte_acelasi_tenant(app):
    from services.activity_service import get_activity_form_context

    ids = _seed(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        ctx = get_activity_form_context(
            current_user=_FakeUser(),
            tenant_id=ids['tenant_a'],
        )

    proiecte_ids = {p.id for p in ctx['proiecte']}
    assert ids['proiect_a'] in proiecte_ids
    assert ids['proiect_b'] not in proiecte_ids


def test_form_context_doar_angajati_acelasi_tenant(app):
    from services.activity_service import get_activity_form_context

    ids = _seed(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        ctx = get_activity_form_context(
            current_user=_FakeUser(),
            tenant_id=ids['tenant_a'],
        )

    angajati_ids = {a.id for a in ctx['angajati']}
    assert ids['ang_a'] in angajati_ids
    assert ids['ang_b'] not in angajati_ids


def test_form_context_doar_santiere_acelasi_tenant(app):
    from services.activity_service import get_activity_form_context

    ids = _seed(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        ctx = get_activity_form_context(
            current_user=_FakeUser(),
            tenant_id=ids['tenant_a'],
        )

    santiere_ids = {s.id for s in ctx['santiere']}
    assert ids['site_a'] in santiere_ids
    assert ids['site_b'] not in santiere_ids


def test_form_context_nu_expune_santiere_straine(app):
    """Contextul de formular nu trebuie sa scurga ID-uri BIM (santiere) straine."""
    from services.activity_service import get_activity_form_context

    ids = _seed(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        ctx = get_activity_form_context(
            current_user=_FakeUser(),
            tenant_id=ids['tenant_b'],
        )

    santiere_ids = {s.id for s in ctx['santiere']}
    assert ids['site_b'] in santiere_ids
    assert ids['site_a'] not in santiere_ids


def test_strict_fara_tenant_fail_closed(app):
    """Strict + user normal fara tenant -> contextul revine gol (fail closed)."""
    from services.activity_service import get_activity_panel_context

    _seed(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        ctx = get_activity_panel_context(
            filters={},
            current_user=_FakeUser(rol='manager'),
            tenant_id=None,
        )

    assert ctx['activitati_recente'] == []
    assert ctx['angajati'] == []
    assert ctx['proiecte'] == []


def test_off_mode_pastreaza_vizibilitatea_legacy(app):
    """In off mode contextul nu filtreaza pe tenant (compatibilitate legacy)."""
    from services.activity_service import get_activity_form_context

    ids = _seed(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'off'
        ctx = get_activity_form_context(
            current_user=_FakeUser(),
            tenant_id=ids['tenant_a'],
        )

    proiecte_ids = {p.id for p in ctx['proiecte']}
    assert ids['proiect_a'] in proiecte_ids
    assert ids['proiect_b'] in proiecte_ids  # off => nefiltrat


# ============================================================
# Fixture data
# ============================================================

def _seed(app):
    from models import (
        Angajat, Proiect, RaportActivitate, Santier, Tenant, db,
    )

    with app.app_context():
        tenant_a = Tenant(cod='test-s11a-a', nume='Tenant S11A A')
        tenant_b = Tenant(cod='test-s11a-b', nume='Tenant S11A B')
        db.session.add_all([tenant_a, tenant_b])
        db.session.commit()

        proiect_a = Proiect(tenant_id=tenant_a.id, cod_proiect='TEST-S11A-PRJ-A',
                            nume='Proiect A', data_start=date(2026, 1, 1), status='activ')
        proiect_b = Proiect(tenant_id=tenant_b.id, cod_proiect='TEST-S11A-PRJ-B',
                            nume='Proiect B', data_start=date(2026, 1, 1), status='activ')
        db.session.add_all([proiect_a, proiect_b])
        db.session.commit()

        ang_a = Angajat(tenant_id=tenant_a.id, nume='S11A-A', prenume='Test',
                        cnp='1900011000101', status='activ', data_angajare=date(2026, 1, 1),
                        email='s11a_a@test.local')
        ang_b = Angajat(tenant_id=tenant_b.id, nume='S11A-B', prenume='Test',
                        cnp='1900011000102', status='activ', data_angajare=date(2026, 1, 1),
                        email='s11a_b@test.local')
        db.session.add_all([ang_a, ang_b])
        db.session.commit()

        site_a = Santier(tenant_id=tenant_a.id, proiect_id=proiect_a.id,
                         cod='TEST-S11A-SITE-A', nume='Site A')
        site_b = Santier(tenant_id=tenant_b.id, proiect_id=proiect_b.id,
                         cod='TEST-S11A-SITE-B', nume='Site B')
        db.session.add_all([site_a, site_b])
        db.session.commit()

        act_a = RaportActivitate(angajat_id=ang_a.id, proiect_id=proiect_a.id,
                                 data=date(2026, 1, 5), tip_activitate='zilnica',
                                 activitate_principala='TEST_S11A_ACT_A')
        act_b = RaportActivitate(angajat_id=ang_b.id, proiect_id=proiect_b.id,
                                 data=date(2026, 1, 5), tip_activitate='zilnica',
                                 activitate_principala='TEST_S11A_ACT_B')
        db.session.add_all([act_a, act_b])
        db.session.commit()

        return {
            'tenant_a': tenant_a.id,
            'tenant_b': tenant_b.id,
            'proiect_a': proiect_a.id,
            'proiect_b': proiect_b.id,
            'ang_a': ang_a.id,
            'ang_b': ang_b.id,
            'site_a': site_a.id,
            'site_b': site_b.id,
            'act_a': act_a.id,
            'act_b': act_b.id,
        }


def _curata(app):
    from models import (
        Angajat, Proiect, RaportActivitate, Santier, Tenant, db,
    )

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        for act in RaportActivitate.query.filter(
            RaportActivitate.activitate_principala.like('TEST_S11A_%')
        ).all():
            db.session.delete(act)
        for site in Santier.query.filter(Santier.cod.like('TEST-S11A-%')).all():
            db.session.delete(site)
        for ang in Angajat.query.filter(Angajat.nume.like('S11A-%')).all():
            db.session.delete(ang)
        for proiect in Proiect.query.filter(Proiect.cod_proiect.like('TEST-S11A-%')).all():
            db.session.delete(proiect)
        for tenant in Tenant.query.filter(Tenant.cod.like('test-s11a-%')).all():
            db.session.delete(tenant)
        db.session.commit()
