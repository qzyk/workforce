"""
Teste unit pentru services.feature_flags.
"""

import pytest

from models import db, FeatureFlag, Tenant
from services import feature_flags as ff


def test_unknown_flag_is_disabled_by_default(app):
    with app.app_context():
        assert ff.is_enabled('inexistent-flag') is False


def test_global_flag_enabled(app):
    with app.app_context():
        ff.set_flag('test-global-on', True)
        # Nou request pentru a evita cache-ul de pe testul anterior
        assert ff.is_enabled('test-global-on') is True


def test_global_flag_disabled_returns_false(app):
    with app.app_context():
        ff.set_flag('test-global-off', False)
        assert ff.is_enabled('test-global-off') is False


def test_tenant_override_beats_global(app):
    with app.app_context():
        # Curat orice tenant existent cu acelasi cod
        Tenant.query.filter_by(cod='test-tn-ff').delete()
        db.session.commit()

        t = Tenant(cod='test-tn-ff', nume='TenantFF', activ=True)
        db.session.add(t)
        db.session.commit()

        ff.set_flag('test-override', False)  # global OFF
        ff.set_flag('test-override', True, tenant_id=t.id)  # tenant ON

        # Pentru tenant t -> True; global -> False
        assert ff.is_enabled('test-override', tenant_id=t.id) is True
        assert ff.is_enabled('test-override', tenant_id=None) is False


def test_set_flag_idempotent_upsert(app):
    with app.app_context():
        ff.set_flag('test-upsert', True, descriere='initial')
        ff.set_flag('test-upsert', False, descriere='actualizat')

        rows = FeatureFlag.query.filter_by(key='test-upsert').all()
        assert len(rows) == 1
        assert rows[0].enabled is False
        assert rows[0].descriere == 'actualizat'


def test_known_flags_catalog_documents_phases():
    """Catalogul KNOWN_FLAGS trebuie sa contina flag-urile principale."""
    expected = {
        'bim-viewer-3d',
        'bim-clash-detection',
        'bim-iot-sensors',
        'bim-realtime-collab',
    }
    assert expected.issubset(set(ff.KNOWN_FLAGS.keys()))


def test_list_flags_global_only(app):
    with app.app_context():
        # Curat
        FeatureFlag.query.delete()
        db.session.commit()

        ff.set_flag('a', True)
        ff.set_flag('b', False)

        flags = ff.list_flags(tenant_id=None)
        keys = sorted(f.key for f in flags)
        assert keys == ['a', 'b']
