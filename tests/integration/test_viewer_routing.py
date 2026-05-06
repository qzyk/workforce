"""
Integration tests pentru routing-ul viewer-ului 3D (Faza 2 BIM).

Verifica ca /bim/viewer/<id>:
- fara feature flag activ -> rendereaza viewer.html (legacy web-ifc)
- cu flag 'bim-viewer-3d' ON -> rendereaza viewer_xeokit.html
- cu ?legacy=1 -> intotdeauna legacy
- cu APS configurat + URN -> redirect la viewer.autodesk.com
"""

import os
import tempfile

import pytest

from models import db, ModelBIM, Santier
from services import feature_flags as ff


@pytest.fixture
def model_ifc(app):
    """Creeaza un ModelBIM IFC cu fisier dummy pe disk."""
    with app.app_context():
        # Fisier IFC dummy (continut ireal, dar route-ul nu il proceseaza)
        upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'ifc')
        os.makedirs(upload_dir, exist_ok=True)
        path = os.path.join(upload_dir, 'test_viewer_routing.ifc')
        with open(path, 'w') as f:
            f.write('ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n')

        m = ModelBIM(
            nume='Test Routing Model',
            tip='ifc',
            fisier_path=os.path.relpath(path, app.root_path),
            fisier_marime=os.path.getsize(path),
        )
        db.session.add(m)
        db.session.commit()
        yield {'id': m.id, 'path': path}

        # Cleanup
        try:
            os.unlink(path)
        except OSError:
            pass


def test_viewer_default_uses_legacy_template(authenticated_client, model_ifc):
    """Fara flag activ: route-ul foloseste viewer.html (legacy web-ifc)."""
    response = authenticated_client.get(f'/bim/viewer/{model_ifc["id"]}')
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    # Marker viewer legacy: include 'web-ifc-viewer' in script
    assert 'web-ifc-viewer' in body, 'Default route ar fi trebuit sa serveasca viewer-ul legacy'
    assert 'xeokit-sdk' not in body or 'xeokit' not in body[:5000], (
        'Nu ar trebui sa apara markeri xeokit pe template-ul legacy'
    )


def test_viewer_with_flag_uses_xeokit_template(app, authenticated_client, model_ifc):
    """Cu flag 'bim-viewer-3d' ON: route-ul foloseste viewer_xeokit.html."""
    with app.app_context():
        ff.set_flag('bim-viewer-3d', True)

    response = authenticated_client.get(f'/bim/viewer/{model_ifc["id"]}')
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'xeokit-sdk' in body, 'Cu flag-ul activ ar trebui sa serveasca viewer_xeokit.html'

    # Cleanup pentru testele urmatoare
    with app.app_context():
        ff.set_flag('bim-viewer-3d', False)


def test_viewer_legacy_query_param_overrides_flag(app, authenticated_client, model_ifc):
    """?legacy=1 forteaza viewer-ul vechi chiar daca flag-ul e ON."""
    with app.app_context():
        ff.set_flag('bim-viewer-3d', True)

    response = authenticated_client.get(f'/bim/viewer/{model_ifc["id"]}?legacy=1')
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'web-ifc-viewer' in body, '?legacy=1 ar trebui sa forteze viewer-ul vechi'

    with app.app_context():
        ff.set_flag('bim-viewer-3d', False)


def test_viewer_redirects_to_aps_when_configured(app, monkeypatch):
    """Daca APS e configurat si modelul are URN APS, redirect la viewer.autodesk.com."""
    monkeypatch.setenv('APS_CLIENT_ID', 'cid')
    monkeypatch.setenv('APS_CLIENT_SECRET', 'csec')

    # Setup TOT intr-un singur context, inclusiv modelul cu URN APS
    upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'ifc')
    os.makedirs(upload_dir, exist_ok=True)
    path = os.path.join(upload_dir, 'test_aps_redirect.ifc')
    with open(path, 'w') as f:
        f.write('ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n')

    with app.app_context():
        # Admin user pentru autentificare
        from models import Utilizator
        u = Utilizator.query.filter_by(email='admin_aps@test.local').first()
        if not u:
            u = Utilizator(nume='APS', prenume='Admin', email='admin_aps@test.local',
                           rol='admin', activ=True)
            u.set_password('aps_pass_123')
            db.session.add(u)

        ff.set_flag('bim-aps-adapter', True, commit=False)
        m = ModelBIM(
            nume='Test APS Model',
            tip='ifc',
            fisier_path=os.path.relpath(path, app.root_path),
            fisier_marime=os.path.getsize(path),
            extern_id='urn:adsk.objects:os.object/bucket/file.ifc',
            source_system='autodesk',
        )
        db.session.add(m)
        db.session.commit()
        mid = m.id

    try:
        client = app.test_client()
        client.post('/auth/login', data={
            'email': 'admin_aps@test.local',
            'parola': 'aps_pass_123',
        }, follow_redirects=False)

        response = client.get(f'/bim/viewer/{mid}', follow_redirects=False)
        assert response.status_code in (301, 302), (
            f'Ar trebui sa redirecteze la APS Viewer, got {response.status_code}. '
            f'Body: {response.get_data(as_text=True)[:200]}'
        )
        assert 'viewer.autodesk.com' in response.location
    finally:
        with app.app_context():
            ff.set_flag('bim-aps-adapter', False)
        try:
            os.unlink(path)
        except OSError:
            pass


def test_viewer_404_when_not_ifc(authenticated_client, app):
    """Modelele non-IFC nu primesc viewer-ul (redirect cu flash)."""
    with app.app_context():
        m = ModelBIM(nume='External', tip='viewer_extern', extern_url='https://example.com')
        db.session.add(m)
        db.session.commit()
        mid = m.id

    response = authenticated_client.get(f'/bim/viewer/{mid}', follow_redirects=False)
    assert response.status_code == 302  # redirect la dashboard


def test_viewer_requires_login(client, model_ifc):
    """Anonim e redirectat la /auth/login."""
    response = client.get(f'/bim/viewer/{model_ifc["id"]}', follow_redirects=False)
    assert response.status_code == 302
    assert '/auth/login' in response.location
