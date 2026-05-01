"""
Smoke tests pentru rutele BIM.
"""

import pytest


def test_bim_dashboard_protected(client):
    """BIM dashboard cere autentificare."""
    resp = client.get('/bim/', follow_redirects=False)
    assert resp.status_code in (302, 401)


def test_bim_dashboard_admin(authenticated_client):
    """Admin accesează dashboard BIM."""
    resp = authenticated_client.get('/bim/')
    assert resp.status_code == 200
    assert b'BIM' in resp.data


def test_bim_santiere_lista(authenticated_client):
    """Lista șantiere se încarcă."""
    resp = authenticated_client.get('/bim/santiere')
    assert resp.status_code == 200


def test_bim_elemente_lista(authenticated_client):
    """Lista elemente se încarcă."""
    resp = authenticated_client.get('/bim/elemente')
    assert resp.status_code == 200


def test_bim_issues_lista(authenticated_client):
    """Lista issues se încarcă."""
    resp = authenticated_client.get('/bim/issues')
    assert resp.status_code == 200


def test_bim_api_tree_returns_json(authenticated_client):
    """API tree întoarce JSON valid."""
    resp = authenticated_client.get('/bim/api/tree')
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)


def test_bim_api_elemente_returns_json(authenticated_client):
    """API elemente întoarce JSON valid."""
    resp = authenticated_client.get('/bim/api/elemente')
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)


def test_bim_santier_nou_form_admin(authenticated_client):
    """Admin poate accesa formularul de șantier nou."""
    resp = authenticated_client.get('/bim/santier/nou')
    assert resp.status_code == 200


def test_bim_santier_create_via_post(app, authenticated_client):
    """POST către /bim/santier/nou creează entitatea în DB."""
    from models import db, Santier
    with app.app_context():
        Santier.query.filter_by(cod='SMOKE-001').delete()
        db.session.commit()

    resp = authenticated_client.post('/bim/santier/nou', data={
        'cod': 'SMOKE-001',
        'nume': 'Smoke Test Santier',
        'oras': 'Bucuresti',
    }, follow_redirects=False)
    assert resp.status_code in (302, 200)

    with app.app_context():
        s = Santier.query.filter_by(cod='SMOKE-001').first()
        assert s is not None
        assert s.nume == 'Smoke Test Santier'
        # Cleanup
        db.session.delete(s)
        db.session.commit()
