"""
Smoke tests - verifica ca rutele cheie raspund (status 200/302) si ca aplicatia porneste.
Aceste teste BLOCHEAZA orice merge care strica functionalitatea de baza.
"""

import pytest


def test_app_creates(app):
    """App-ul se creeaza fara erori."""
    assert app is not None
    assert 'SQLALCHEMY_DATABASE_URI' in app.config


def test_db_creates_tables(app):
    """DB are toate tabelele asteptate."""
    from models import db
    from sqlalchemy import inspect
    with app.app_context():
        insp = inspect(db.engine)
        tables = insp.get_table_names()
    expected = {
        'utilizatori', 'angajati', 'proiecte', 'pontaje', 'documente',
        'rapoarte_activitati', 'tipuri_instalatii', 'masini',
    }
    missing = expected - set(tables)
    assert not missing, f'Tabele lipsa: {missing}'


def test_login_page_renders(client):
    """Pagina de login se incarca cu form."""
    resp = client.get('/auth/login')
    assert resp.status_code == 200
    assert b'parola' in resp.data.lower() or b'password' in resp.data.lower()


def test_dashboard_redirects_when_unauthenticated(client):
    """Dashboard cere autentificare."""
    resp = client.get('/', follow_redirects=False)
    assert resp.status_code in (302, 401)


@pytest.mark.parametrize('url', [
    '/activitati/',
    '/angajati/',
    '/proiecte/',
    '/pontaje/',
    '/documente/',
])
def test_protected_routes_redirect(client, url):
    """Rutele protejate redirect la login pentru utilizatori neauten."""
    resp = client.get(url, follow_redirects=False)
    assert resp.status_code in (302, 401), f'{url} ar trebui sa redirect-eze, am primit {resp.status_code}'


def test_admin_can_access_dashboard(authenticated_client):
    """Admin autentificat poate accesa dashboard."""
    resp = authenticated_client.get('/')
    assert resp.status_code in (200, 302)


def test_admin_can_access_activitati(authenticated_client):
    """Admin poate accesa lista activitati."""
    resp = authenticated_client.get('/activitati/')
    assert resp.status_code == 200
