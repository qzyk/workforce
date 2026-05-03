"""
Tests permisiuni: ce poate face fiecare rol (admin / manager / operator).
"""

import pytest


class TestOperatorRestrictions:
    """Operator nu poate accesa rute manager_or_admin."""

    def test_operator_cannot_create_santier(self, app, operator_client):
        """POST /bim/santier/nou pentru operator -> redirect cu warning."""
        resp = operator_client.post('/bim/santier/nou', data={
            'cod': 'OP-S-001',
            'nume': 'Op tries',
        }, follow_redirects=False)
        # Operatorul ar trebui sa fie redirectat (nu autorizat)
        assert resp.status_code in (302, 403)

        # Verific ca santierul nu s-a creat
        from models import db, Santier
        with app.app_context():
            assert Santier.query.filter_by(cod='OP-S-001').first() is None

    def test_operator_cannot_access_quality_report(self, operator_client):
        """Pagina /bim/quality e admin/manager only."""
        resp = operator_client.get('/bim/quality', follow_redirects=False)
        assert resp.status_code in (302, 403)

    def test_operator_can_view_bim_dashboard(self, operator_client):
        """Operator POATE vedea dashboard-ul (read-only)."""
        resp = operator_client.get('/bim/')
        assert resp.status_code == 200

    def test_operator_can_view_elemente(self, operator_client):
        resp = operator_client.get('/bim/elemente')
        assert resp.status_code == 200

    def test_operator_can_view_issues(self, operator_client):
        resp = operator_client.get('/bim/issues')
        assert resp.status_code == 200


class TestAdminCanDoAll:
    """Admin are toate drepturile."""

    def test_admin_can_create_santier(self, app, authenticated_client):
        from models import db, Santier
        resp = authenticated_client.post('/bim/santier/nou', data={
            'cod': 'AD-S-001',
            'nume': 'Admin santier',
        }, follow_redirects=False)
        assert resp.status_code in (200, 302)

        with app.app_context():
            assert Santier.query.filter_by(cod='AD-S-001').first() is not None

    def test_admin_can_access_quality(self, authenticated_client):
        resp = authenticated_client.get('/bim/quality')
        assert resp.status_code == 200

    def test_admin_can_run_validate_bim_via_api(self, authenticated_client):
        resp = authenticated_client.get('/bim/api/quality')
        assert resp.status_code == 200


class TestUnauthenticatedAccess:
    """Toate rutele protejate redirect la login."""

    @pytest.mark.parametrize('url', [
        '/bim/',
        '/bim/santiere',
        '/bim/santier/nou',
        '/bim/elemente',
        '/bim/issues',
        '/bim/modele',
        '/bim/quality',
        '/bim/import/ifc',
        '/activitati/',
        '/activitati/adauga',
    ])
    def test_unauthenticated_redirects(self, client, url):
        resp = client.get(url, follow_redirects=False)
        assert resp.status_code in (302, 401), f'{url} ar trebui sa redirect-eze'
