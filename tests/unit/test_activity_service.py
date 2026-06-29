"""Teste directe pentru services/activity_service.py (S1.1A).

Verifica boundary-ul de serviciu pentru contextul de citire/formular al
activitatilor: scoping tenant pe panou si pe dropdown-urile de formular,
comportament pe moduri (off/strict) si fail-closed pentru user fara tenant.
"""

from datetime import date

import pytest
from werkzeug.exceptions import HTTPException


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
# S1.1B — save (create/edit) extraction
# ============================================================

def _form(data):
    """Construieste un MultiDict similar request.form din dict-ul de test."""
    from werkzeug.datastructures import MultiDict

    md = MultiDict()
    for k, v in data.items():
        if isinstance(v, (list, tuple)):
            for item in v:
                md.add(k, str(item))
        else:
            md.add(k, str(v))
    return md


def test_save_creeaza_activitate_cu_campurile_corecte(app):
    from services.activity_service import save_activity_from_form_data

    ids = _seed(app)

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        with app.test_request_context('/'):
            rezultat = save_activity_from_form_data(
                activity=None,
                form_data=_form({
                    'angajat_id': ids['ang_a'],
                    'proiect_ids[]': [ids['proiect_a']],
                    'data': '2026-02-10',
                    'activitate_principala': 'TEST_S11A_SAVE_CREATE',
                    'tip_activitate': 'zilnica',
                    'actiune': 'draft',
                }),
                current_user=_FakeUser(),
            )

        act = rezultat['activity']
        assert rezultat['actiune'] == 'draft'
        assert act.id is not None
        assert act.angajat_id == ids['ang_a']
        assert act.proiect_id == ids['proiect_a']
        assert act.activitate_principala == 'TEST_S11A_SAVE_CREATE'
        assert act.data == date(2026, 2, 10)
        assert act.tip_activitate == 'zilnica'
        assert act.status == 'draft'

        # Persistat in DB
        from models import RaportActivitate
        reincarcat = RaportActivitate.query.get(act.id)
        assert reincarcat is not None
        assert reincarcat.activitate_principala == 'TEST_S11A_SAVE_CREATE'


def test_save_editeaza_activitate_existenta(app):
    from services.activity_service import save_activity_from_form_data
    from models import RaportActivitate

    ids = _seed(app)

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        with app.test_request_context('/'):
            creat = save_activity_from_form_data(
                activity=None,
                form_data=_form({
                    'angajat_id': ids['ang_a'],
                    'proiect_ids[]': [ids['proiect_a']],
                    'data': '2026-02-10',
                    'activitate_principala': 'TEST_S11A_SAVE_EDIT_ORIG',
                    'actiune': 'draft',
                }),
                current_user=_FakeUser(),
            )['activity']
            orig_id = creat.id

            existing = RaportActivitate.query.get(orig_id)
            editat = save_activity_from_form_data(
                activity=existing,
                form_data=_form({
                    'angajat_id': ids['ang_a'],
                    'proiect_ids[]': [ids['proiect_a']],
                    'data': '2026-02-11',
                    'activitate_principala': 'TEST_S11A_SAVE_EDIT_NOU',
                    'actiune': 'draft',
                }),
                current_user=_FakeUser(),
            )['activity']

        assert editat.id == orig_id  # acelasi rand, update nu insert
        assert editat.activitate_principala == 'TEST_S11A_SAVE_EDIT_NOU'
        assert editat.data == date(2026, 2, 11)


def test_save_actiune_trimite_seteaza_status_trimis(app):
    from services.activity_service import save_activity_from_form_data

    ids = _seed(app)

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        with app.test_request_context('/'):
            act = save_activity_from_form_data(
                activity=None,
                form_data=_form({
                    'angajat_id': ids['ang_a'],
                    'proiect_ids[]': [ids['proiect_a']],
                    'data': '2026-02-10',
                    'activitate_principala': 'TEST_S11A_SAVE_TRIMITE',
                    'actiune': 'trimite',
                }),
                current_user=_FakeUser(),
            )['activity']

        assert act.status == 'trimis'


def test_save_respins_revine_la_draft(app):
    from services.activity_service import save_activity_from_form_data
    from models import RaportActivitate, db

    ids = _seed(app)

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        respinsa = RaportActivitate(
            angajat_id=ids['ang_a'], proiect_id=ids['proiect_a'],
            data=date(2026, 2, 9), tip_activitate='zilnica',
            activitate_principala='TEST_S11A_SAVE_RESPINS', status='respins',
        )
        db.session.add(respinsa)
        db.session.commit()
        respinsa_id = respinsa.id

        with app.test_request_context('/'):
            existing = RaportActivitate.query.get(respinsa_id)
            editat = save_activity_from_form_data(
                activity=existing,
                form_data=_form({
                    'angajat_id': ids['ang_a'],
                    'proiect_ids[]': [ids['proiect_a']],
                    'data': '2026-02-09',
                    'activitate_principala': 'TEST_S11A_SAVE_RESPINS',
                    'actiune': 'draft',
                }),
                current_user=_FakeUser(),
            )['activity']

        assert editat.status == 'draft'


def test_save_supervisor_egal_cu_angajat_este_curatat(app):
    from services.activity_service import save_activity_from_form_data

    ids = _seed(app)

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        with app.test_request_context('/'):
            act = save_activity_from_form_data(
                activity=None,
                form_data=_form({
                    'angajat_id': ids['ang_a'],
                    'proiect_ids[]': [ids['proiect_a']],
                    'supervisor_id': ids['ang_a'],
                    'data': '2026-02-10',
                    'activitate_principala': 'TEST_S11A_SAVE_SUPERVISOR',
                    'actiune': 'draft',
                }),
                current_user=_FakeUser(),
            )['activity']

        assert act.supervisor_id is None


def test_save_nu_creeaza_sau_modifica_pontaj(app):
    from services.activity_service import save_activity_from_form_data
    from models import Pontaj

    ids = _seed(app)

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        pontaje_inainte = Pontaj.query.count()
        with app.test_request_context('/'):
            save_activity_from_form_data(
                activity=None,
                form_data=_form({
                    'angajat_id': ids['ang_a'],
                    'proiect_ids[]': [ids['proiect_a']],
                    'data': '2026-02-10',
                    'activitate_principala': 'TEST_S11A_SAVE_NOPONTAJ',
                    'actiune': 'draft',
                }),
                current_user=_FakeUser(),
            )
        assert Pontaj.query.count() == pontaje_inainte


def test_save_proiect_lipsa_ridica_validation_error(app):
    from services.activity_service import (
        save_activity_from_form_data, ActivityValidationError,
    )

    ids = _seed(app)

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        with app.test_request_context('/'):
            with pytest.raises(ActivityValidationError):
                save_activity_from_form_data(
                    activity=None,
                    form_data=_form({
                        'angajat_id': ids['ang_a'],
                        'data': '2026-02-10',
                        'activitate_principala': 'TEST_S11A_SAVE_NOPROJ',
                        'actiune': 'draft',
                    }),
                    current_user=_FakeUser(),
                )


def test_save_proiect_strain_respins_inainte_de_mutatie(app):
    from services.activity_service import save_activity_from_form_data
    from models import RaportActivitate

    ids = _seed(app)

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        inainte = RaportActivitate.query.filter_by(proiect_id=ids['proiect_b']).count()
        with app.test_request_context('/'):
            from flask import g
            g.tenant_override = ids['tenant_a']
            with pytest.raises(HTTPException) as exc:
                save_activity_from_form_data(
                    activity=None,
                    form_data=_form({
                        'angajat_id': ids['ang_a'],
                        'proiect_ids[]': [ids['proiect_b']],  # proiect din tenant B
                        'data': '2026-02-10',
                        'activitate_principala': 'TEST_S11A_SAVE_FOREIGNPRJ',
                        'actiune': 'draft',
                    }),
                    current_user=_FakeUser(rol='manager', tenant_id=ids['tenant_a']),
                )
        assert exc.value.code == 404
        # Fara mutatie partiala
        assert RaportActivitate.query.filter_by(proiect_id=ids['proiect_b']).count() == inainte


def test_save_angajat_strain_respins(app):
    from services.activity_service import save_activity_from_form_data

    ids = _seed(app)

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            from flask import g
            g.tenant_override = ids['tenant_a']
            with pytest.raises(HTTPException) as exc:
                save_activity_from_form_data(
                    activity=None,
                    form_data=_form({
                        'angajat_id': ids['ang_b'],  # angajat din tenant B
                        'proiect_ids[]': [ids['proiect_a']],
                        'data': '2026-02-10',
                        'activitate_principala': 'TEST_S11A_SAVE_FOREIGNANG',
                        'actiune': 'draft',
                    }),
                    current_user=_FakeUser(rol='manager', tenant_id=ids['tenant_a']),
                )
        assert exc.value.code == 404


def test_save_context_bim_strain_respins(app):
    from services.activity_service import save_activity_from_form_data

    ids = _seed(app)

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            from flask import g
            g.tenant_override = ids['tenant_a']
            with pytest.raises(HTTPException) as exc:
                save_activity_from_form_data(
                    activity=None,
                    form_data=_form({
                        'angajat_id': ids['ang_a'],
                        'proiect_ids[]': [ids['proiect_a']],
                        'bim_santier_id': ids['site_b'],  # santier din tenant B
                        'data': '2026-02-10',
                        'activitate_principala': 'TEST_S11A_SAVE_FOREIGNBIM',
                        'actiune': 'draft',
                    }),
                    current_user=_FakeUser(rol='manager', tenant_id=ids['tenant_a']),
                )
        assert exc.value.code == 404


def test_save_strict_fara_tenant_fail_closed(app):
    from services.activity_service import save_activity_from_form_data

    ids = _seed(app)

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'strict'
        with app.test_request_context('/'):
            with pytest.raises(HTTPException) as exc:
                save_activity_from_form_data(
                    activity=None,
                    form_data=_form({
                        'angajat_id': ids['ang_a'],
                        'proiect_ids[]': [ids['proiect_a']],
                        'data': '2026-02-10',
                        'activitate_principala': 'TEST_S11A_SAVE_NOTENANT',
                        'actiune': 'draft',
                    }),
                    current_user=_FakeUser(rol='manager'),
                )
        assert exc.value.code == 403


def test_save_off_mode_accepta_proiect_indiferent_de_tenant(app):
    from services.activity_service import save_activity_from_form_data

    ids = _seed(app)

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        with app.test_request_context('/'):
            act = save_activity_from_form_data(
                activity=None,
                form_data=_form({
                    'angajat_id': ids['ang_a'],
                    'proiect_ids[]': [ids['proiect_b']],  # alt tenant, dar off => permis
                    'data': '2026-02-10',
                    'activitate_principala': 'TEST_S11A_SAVE_OFFLEGACY',
                    'actiune': 'draft',
                }),
                current_user=_FakeUser(),
            )['activity']
        assert act.proiect_id == ids['proiect_b']


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
