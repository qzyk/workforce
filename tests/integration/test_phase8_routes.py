"""
Integration tests pentru rutele Faza 8.
"""

import json
import pytest

from models import db, BIMRoleAssignment, ApiToken, IssueBIM, Santier
from services import feature_flags as ff
from services import api_tokens as svc_tokens


# ====================================================
# ROLES
# ====================================================

def test_roles_lista_redirects_when_flag_off(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-rbac-fine', False)
    resp = authenticated_client.get('/bim/roles', follow_redirects=False)
    assert resp.status_code == 302


def test_roles_lista_renders_when_flag_on(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-rbac-fine', True)
    resp = authenticated_client.get('/bim/roles')
    assert resp.status_code == 200


def test_create_role_via_route(authenticated_client, app, admin_user):
    with app.app_context():
        ff.set_flag('bim-rbac-fine', True)
        BIMRoleAssignment.query.delete()
        db.session.commit()

    resp = authenticated_client.post('/bim/role/nou', data={
        'user_id': admin_user.id, 'rol': 'reviewer',
        'scope_type': 'global', 'scope_id': '',
    }, follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        a = BIMRoleAssignment.query.filter_by(user_id=admin_user.id).first()
        assert a is not None
        assert a.rol == 'reviewer'


# ====================================================
# TOKENS
# ====================================================

def test_tokens_redirects_when_flag_off(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-public-api', False)
    resp = authenticated_client.get('/bim/tokens', follow_redirects=False)
    assert resp.status_code == 302


def test_tokens_renders_when_flag_on(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-public-api', True)
    resp = authenticated_client.get('/bim/tokens')
    assert resp.status_code == 200


def test_create_token_via_route(authenticated_client, app, admin_user):
    with app.app_context():
        ff.set_flag('bim-public-api', True)
        ApiToken.query.delete()
        db.session.commit()

    resp = authenticated_client.post('/bim/token/nou', data={
        'nume': 'Test token',
        'scopes': ['bim:read', 'iot:read'],
    }, follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        tokens = ApiToken.query.filter_by(owner_id=admin_user.id).all()
        assert len(tokens) == 1
        assert 'bim:read' in tokens[0].scopes


# ====================================================
# COBIE EXPORT
# ====================================================

def test_cobie_export_disabled(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-cobie-export', False)
        s = Santier(cod='S-CBN', nume='X'); db.session.add(s); db.session.commit()
        sid = s.id
    resp = authenticated_client.get(f'/bim/santier/{sid}/cobie.xlsx',
                                    follow_redirects=False)
    assert resp.status_code == 302


def test_cobie_export_returns_xlsx(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-cobie-export', True)
        s = Santier(cod='S-CB-OK', nume='OK'); db.session.add(s); db.session.commit()
        sid = s.id
    resp = authenticated_client.get(f'/bim/santier/{sid}/cobie.xlsx')
    assert resp.status_code == 200
    assert 'spreadsheetml' in resp.headers.get('Content-Type', '')


# ====================================================
# BCF EXPORT
# ====================================================

def test_bcf_export_disabled(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-bcf-full', False)
    resp = authenticated_client.get('/bim/issues/export-bcf', follow_redirects=False)
    assert resp.status_code == 302


def test_bcf_export_empty_redirects(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-bcf-full', True)
        IssueBIM.query.delete()
        db.session.commit()
    resp = authenticated_client.get('/bim/issues/export-bcf', follow_redirects=False)
    # Redirect cu flash warning
    assert resp.status_code == 302


def test_bcf_export_with_issues_returns_zip(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-bcf-full', True)
        IssueBIM.query.delete()
        iss = IssueBIM(titlu='Test BCF', tip='defect', severitate='mare',
                       status='deschis')
        db.session.add(iss); db.session.commit()
    resp = authenticated_client.get('/bim/issues/export-bcf')
    assert resp.status_code == 200
    # zip starts with PK
    assert resp.data[:2] == b'PK'


# ====================================================
# OPENAPI
# ====================================================

def test_openapi_spec_is_public(client):
    """OpenAPI spec accesibil fara auth."""
    resp = client.get('/bim/api/openapi.json')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['openapi'].startswith('3.')
    assert 'paths' in data
    assert 'components' in data
    # Endpoint-uri cunoscute
    assert '/bim/api/sensors/ingest' in data['paths']


def test_api_docs_page_renders(client):
    resp = client.get('/bim/api/docs')
    # Pagina cu Swagger UI - publica
    assert resp.status_code == 200
    assert b'swagger' in resp.data.lower()


# ====================================================
# PUBLIC API v1 (token-auth)
# ====================================================

def test_api_v1_issues_requires_token(client, app):
    resp = client.get('/bim/api/v1/issues')
    assert resp.status_code == 401


def test_api_v1_issues_with_token(client, app, admin_user):
    with app.app_context():
        # Curatam orice token vechi
        ApiToken.query.delete()
        db.session.commit()
        tok = svc_tokens.create_token('test API', admin_user.id, ['bim:read'])
        token_str = tok.token

        # Add un issue
        IssueBIM.query.delete()
        iss = IssueBIM(titlu='Public API test', tip='defect',
                       severitate='medie', status='deschis')
        db.session.add(iss); db.session.commit()

    resp = client.get('/bim/api/v1/issues',
                       headers={'Authorization': f'Bearer {token_str}'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['count'] >= 1
    assert any('Public API test' in str(d.get('titlu')) for d in data['data'])


def test_api_v1_issues_invalid_token(client):
    resp = client.get('/bim/api/v1/issues',
                       headers={'Authorization': 'Bearer xxx'})
    assert resp.status_code == 401


def test_api_v1_issues_missing_scope(client, app, admin_user):
    """Token cu scope diferit de bim:read e respins."""
    with app.app_context():
        ApiToken.query.delete()
        db.session.commit()
        tok = svc_tokens.create_token('iot only', admin_user.id, ['iot:read'])
        token_str = tok.token
    resp = client.get('/bim/api/v1/issues',
                       headers={'Authorization': f'Bearer {token_str}'})
    assert resp.status_code == 403


def test_api_v1_via_xapitoken_header(client, app, admin_user):
    """Suporta si X-Api-Token in plus de Authorization: Bearer."""
    with app.app_context():
        ApiToken.query.delete()
        db.session.commit()
        tok = svc_tokens.create_token('xat', admin_user.id, ['bim:read'])
        token_str = tok.token
    resp = client.get('/bim/api/v1/issues',
                       headers={'X-Api-Token': token_str})
    assert resp.status_code == 200
