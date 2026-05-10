"""
Integration tests pentru routes Faza 3 (versioning + federation).
"""

import pytest

from models import db, BIMModelVersion, ModelBIM, Santier, AuditLog
from services import feature_flags as ff


# ====================================================
# Feature flag gating
# ====================================================

def test_versiuni_route_redirects_when_flag_off(authenticated_client, app):
    """Cand 'bim-model-versioning' e OFF, ruta redirectioneaza la dashboard."""
    with app.app_context():
        ff.set_flag('bim-model-versioning', False)
        m = ModelBIM(nume='M-OFF', tip='ifc')
        db.session.add(m)
        db.session.commit()
        mid = m.id

    resp = authenticated_client.get(f'/bim/model/{mid}/versiuni', follow_redirects=False)
    assert resp.status_code == 302
    assert '/bim' in resp.headers.get('Location', '')


def test_versiuni_route_renders_when_flag_on(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-model-versioning', True)
        m = ModelBIM(nume='M-ON', tip='ifc')
        db.session.add(m)
        db.session.commit()
        mid = m.id

    resp = authenticated_client.get(f'/bim/model/{mid}/versiuni')
    assert resp.status_code == 200
    assert b'Versiuni' in resp.data


def test_api_versiuni_returns_disabled_when_flag_off(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-model-versioning', False)
        m = ModelBIM(nume='M-API-OFF', tip='ifc')
        db.session.add(m)
        db.session.commit()
        mid = m.id

    resp = authenticated_client.get(f'/bim/api/model/{mid}/versiuni')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['enabled'] is False
    assert data['versions'] == []


def test_api_versiuni_returns_list_when_flag_on(authenticated_client, app, admin_user):
    from services import bim_workflow
    with app.app_context():
        ff.set_flag('bim-model-versioning', True)
        m = ModelBIM(nume='M-API-ON', tip='ifc')
        db.session.add(m)
        db.session.commit()
        bim_workflow.create_new_version(m, 'v1.0', admin_user, disciplina='ARH')
        bim_workflow.create_new_version(m, 'v2.0', admin_user, disciplina='ARH')
        mid = m.id

    resp = authenticated_client.get(f'/bim/api/model/{mid}/versiuni')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['enabled'] is True
    assert data['count'] == 2
    versions = sorted(data['versions'], key=lambda v: v['versiune'])
    assert versions[0]['versiune'] == 'v1.0'
    assert versions[0]['status'] == 'wip'


# ====================================================
# Workflow transitions via routes (with audit)
# ====================================================

def test_creating_version_writes_audit_log(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-model-versioning', True)
        AuditLog.query.delete()
        BIMModelVersion.query.delete()
        m = ModelBIM(nume='M-AUD', tip='ifc')
        db.session.add(m)
        db.session.commit()
        mid = m.id

    resp = authenticated_client.post(f'/bim/model/{mid}/versiune-noua', data={
        'versiune': 'v1.0', 'disciplina': 'ARH', 'descriere': 'init',
    }, follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        # 1 versiune creata + 1 audit log
        assert BIMModelVersion.query.filter_by(model_id=mid).count() == 1
        rows = AuditLog.query.filter_by(entity_type='bim_model_version', action='create').all()
        assert len(rows) == 1


def test_transition_endpoint_audits(authenticated_client, app, admin_user):
    from services import bim_workflow
    with app.app_context():
        ff.set_flag('bim-model-versioning', True)
        AuditLog.query.delete()
        BIMModelVersion.query.delete()
        m = ModelBIM(nume='M-TRANS', tip='ifc')
        db.session.add(m)
        db.session.commit()
        v = bim_workflow.create_new_version(m, 'v1.0', admin_user)
        vid = v.id

    resp = authenticated_client.post(
        f'/bim/model-version/{vid}/transition',
        data={'status': 'shared'}, follow_redirects=False,
    )
    assert resp.status_code == 302

    with app.app_context():
        v_after = BIMModelVersion.query.get(vid)
        assert v_after.status == 'shared'
        rows = AuditLog.query.filter_by(
            entity_type='bim_model_version', action='workflow_shared',
        ).all()
        assert len(rows) == 1


def test_invalid_transition_rejected_with_flash(authenticated_client, app, admin_user):
    from services import bim_workflow
    with app.app_context():
        ff.set_flag('bim-model-versioning', True)
        BIMModelVersion.query.delete()
        m = ModelBIM(nume='M-INV', tip='ifc')
        db.session.add(m)
        db.session.commit()
        v = bim_workflow.create_new_version(m, 'v1.0', admin_user)
        vid = v.id

    # wip -> published direct nu e permis
    resp = authenticated_client.post(
        f'/bim/model-version/{vid}/transition',
        data={'status': 'published'}, follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        v_after = BIMModelVersion.query.get(vid)
        # Status ramane neschimbat
        assert v_after.status == 'wip'


# ====================================================
# Federation
# ====================================================

def test_federation_route_redirects_when_flag_off(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-federation', False)
        s = Santier(cod='S-FED-OFF', nume='Test')
        db.session.add(s)
        db.session.commit()
        sid = s.id
    resp = authenticated_client.get(f'/bim/santier/{sid}/viewer-federat',
                                     follow_redirects=False)
    assert resp.status_code == 302


def test_federation_route_redirects_when_no_published_models(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-federation', True)
        s = Santier(cod='S-FED-EMPTY', nume='Empty')
        db.session.add(s)
        db.session.commit()
        sid = s.id
    resp = authenticated_client.get(f'/bim/santier/{sid}/viewer-federat',
                                     follow_redirects=False)
    # Redirect cu warning - niciun model publicat
    assert resp.status_code == 302
