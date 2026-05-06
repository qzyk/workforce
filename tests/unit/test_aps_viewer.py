"""
Teste unit pentru services.aps_viewer (APS adapter stub - Faza 2 BIM).
"""

import os
import pytest

from models import db, ModelBIM, ExternalMapping
from services import aps_viewer
from services import feature_flags as ff


@pytest.fixture(autouse=True)
def _clear_aps_env(monkeypatch):
    """Sterge env vars APS la fiecare test ca sa avem control complet."""
    monkeypatch.delenv('APS_CLIENT_ID', raising=False)
    monkeypatch.delenv('APS_CLIENT_SECRET', raising=False)
    monkeypatch.delenv('APS_BUCKET_KEY', raising=False)


def test_has_credentials_false_when_env_missing():
    assert aps_viewer.has_credentials() is False


def test_has_credentials_true_with_env(monkeypatch):
    monkeypatch.setenv('APS_CLIENT_ID', 'cid_xyz')
    monkeypatch.setenv('APS_CLIENT_SECRET', 'csec_xyz')
    assert aps_viewer.has_credentials() is True


def test_is_configured_requires_both_flag_and_credentials(app, monkeypatch):
    with app.app_context():
        # Caz 1: flag OFF + credentiale absente -> False
        assert aps_viewer.is_configured() is False

        # Caz 2: flag ON dar credentiale absente -> False
        ff.set_flag('bim-aps-adapter', True)
        assert aps_viewer.is_configured() is False

        # Caz 3: flag ON + credentiale prezente -> True
        monkeypatch.setenv('APS_CLIENT_ID', 'cid')
        monkeypatch.setenv('APS_CLIENT_SECRET', 'csec')
        assert aps_viewer.is_configured() is True

        # Caz 4: flag OFF + credentiale prezente -> False
        ff.set_flag('bim-aps-adapter', False)
        assert aps_viewer.is_configured() is False


def test_get_viewer_url_returns_none_when_not_configured(app):
    with app.app_context():
        m = ModelBIM(nume='Test Model', tip='ifc')
        db.session.add(m)
        db.session.flush()
        assert aps_viewer.get_viewer_url(m) is None


def test_get_viewer_url_with_extern_id_on_model(app, monkeypatch):
    """Daca modelul are extern_id direct + source_system='autodesk', se foloseste."""
    monkeypatch.setenv('APS_CLIENT_ID', 'cid')
    monkeypatch.setenv('APS_CLIENT_SECRET', 'csec')
    with app.app_context():
        ff.set_flag('bim-aps-adapter', True)
        m = ModelBIM(
            nume='APS Model',
            tip='ifc',
            extern_id='dXJuOmFkc2sub2JqZWN0czpvcy5vYmplY3QvbXktbW9kZWwuaWZj',
            source_system='autodesk',
        )
        db.session.add(m)
        db.session.flush()

        url = aps_viewer.get_viewer_url(m)
        assert url is not None
        assert 'viewer.autodesk.com' in url
        assert m.extern_id in url


def test_get_viewer_url_via_external_mapping(app, monkeypatch):
    """Daca modelul are URN APS in ExternalMapping, se foloseste de acolo."""
    monkeypatch.setenv('APS_CLIENT_ID', 'cid')
    monkeypatch.setenv('APS_CLIENT_SECRET', 'csec')
    with app.app_context():
        ff.set_flag('bim-aps-adapter', True)
        m = ModelBIM(nume='Mapped Model', tip='ifc')
        db.session.add(m)
        db.session.flush()

        urn = 'urn:adsk.objects:os.object/bucket/file.ifc'
        mapping = ExternalMapping(
            entity_type='model_bim',
            entity_id=m.id,
            source_system='autodesk',
            extern_id=urn,
        )
        db.session.add(mapping)
        db.session.flush()

        url = aps_viewer.get_viewer_url(m)
        assert url is not None
        assert urn in url


def test_status_summary_reflects_state(app, monkeypatch):
    with app.app_context():
        # Stare initiala: nimic
        s = aps_viewer.status_summary()
        assert s['has_credentials'] is False
        assert s['flag_enabled'] is False
        assert s['is_configured'] is False
        assert s['client_id_preview'] is None

        # Cu credentiale + flag
        monkeypatch.setenv('APS_CLIENT_ID', 'abcdefghijkl')
        monkeypatch.setenv('APS_CLIENT_SECRET', 'verysecret')
        ff.set_flag('bim-aps-adapter', True)

        s2 = aps_viewer.status_summary()
        assert s2['has_credentials'] is True
        assert s2['flag_enabled'] is True
        assert s2['is_configured'] is True
        assert s2['client_id_preview'] == 'abcdef...'
