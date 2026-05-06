"""
Teste unit pentru services.audit.
"""

import json
import pytest

from models import db, AuditLog, Santier
from services import audit as audit_svc


def test_log_create_writes_entry(app):
    with app.app_context():
        s = Santier(cod='TEST_AUD_01', nume='Santier Audit')
        db.session.add(s)
        db.session.flush()

        entry = audit_svc.log_create(
            'santier', s.id,
            new_values={'cod': s.cod, 'nume': s.nume},
            commit=True,
        )
        assert entry is not None
        assert entry.action == 'create'
        assert entry.entity_type == 'santier'
        assert entry.entity_id == s.id
        new_vals = json.loads(entry.new_values_json)
        assert new_vals['cod'] == 'TEST_AUD_01'
        assert new_vals['nume'] == 'Santier Audit'
        assert entry.old_values_json is None


def test_log_update_records_only_changed_fields(app):
    with app.app_context():
        s = Santier(cod='TEST_AUD_02', nume='Initial', oras='Cluj')
        db.session.add(s)
        db.session.flush()

        before = audit_svc.snapshot(s, ['cod', 'nume', 'oras'])
        s.nume = 'Updated'
        # 'cod' si 'oras' raman neschimbate

        entry = audit_svc.log_update(
            'santier', s.id, before,
            audit_svc.snapshot(s, ['cod', 'nume', 'oras']),
            commit=True,
        )
        assert entry is not None
        new_vals = json.loads(entry.new_values_json)
        old_vals = json.loads(entry.old_values_json)
        # Doar 'nume' s-a schimbat - 'cod' si 'oras' nu apar
        assert set(new_vals.keys()) == {'nume'}
        assert set(old_vals.keys()) == {'nume'}
        assert old_vals['nume'] == 'Initial'
        assert new_vals['nume'] == 'Updated'


def test_log_update_skips_when_nothing_changed(app):
    with app.app_context():
        s = Santier(cod='TEST_AUD_03', nume='Nemodif')
        db.session.add(s)
        db.session.flush()

        before = audit_svc.snapshot(s, ['cod', 'nume'])
        # Nu modificam nimic
        result = audit_svc.log_update(
            'santier', s.id, before,
            audit_svc.snapshot(s, ['cod', 'nume']),
            commit=True,
        )
        # No-op: returneaza None si nu insereaza nimic
        assert result is None
        rows = AuditLog.query.filter_by(entity_type='santier', entity_id=s.id, action='update').count()
        assert rows == 0


def test_log_delete_records_old_values(app):
    with app.app_context():
        s = Santier(cod='TEST_AUD_04', nume='ToDelete')
        db.session.add(s)
        db.session.flush()
        sid = s.id

        entry = audit_svc.log_delete(
            'santier', sid,
            old_values={'cod': s.cod, 'nume': s.nume},
            commit=True,
        )
        assert entry is not None
        assert entry.action == 'delete'
        old_vals = json.loads(entry.old_values_json)
        assert old_vals['cod'] == 'TEST_AUD_04'


def test_log_failure_does_not_break_main_flow(app, monkeypatch):
    """O eroare in audit nu trebuie sa propage exceptii."""
    with app.app_context():
        # Simulez o eroare la insertia in DB
        def _broken_add(*a, **kw):
            raise RuntimeError('simulated DB failure')
        monkeypatch.setattr(db.session, 'add', _broken_add)

        # Nu trebuie sa arunce
        result = audit_svc.log_create('santier', 999, new_values={'x': 1})
        assert result is None
