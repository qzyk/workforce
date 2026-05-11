"""
Teste unit pentru services.api_tokens.
"""

from datetime import datetime, timedelta
import pytest

from models import db, ApiToken, Utilizator
from services import api_tokens as svc


@pytest.fixture
def owner(app):
    with app.app_context():
        u = Utilizator.query.filter_by(email='tok_owner@test.local').first()
        if not u:
            u = Utilizator(nume='Tok', prenume='X', email='tok_owner@test.local',
                           rol='admin', activ=True)
            u.set_password('x'); db.session.add(u); db.session.commit()
        yield u


def test_create_token_generates_64_hex(app, owner):
    with app.app_context():
        t = svc.create_token('test', owner.id, ['bim:read'])
        assert len(t.token) == 64
        assert t.scopes == ['bim:read']
        assert t.activ is True


def test_create_token_invalid_scope_raises(app, owner):
    with app.app_context():
        with pytest.raises(ValueError):
            svc.create_token('x', owner.id, ['scope_invalid'])


def test_create_token_empty_name_raises(app, owner):
    with app.app_context():
        with pytest.raises(ValueError):
            svc.create_token('', owner.id, ['bim:read'])


def test_authenticate_valid_token(app, owner):
    with app.app_context():
        t = svc.create_token('auth1', owner.id, ['bim:read'])
        result = svc.authenticate_token(t.token)
        assert result is not None
        assert result.id == t.id


def test_authenticate_invalid_token(app):
    with app.app_context():
        assert svc.authenticate_token('xxx') is None
        assert svc.authenticate_token('') is None


def test_authenticate_revoked_token(app, owner):
    with app.app_context():
        t = svc.create_token('auth2', owner.id, ['bim:read'])
        plain_token = t.token
        svc.revoke_token(t)
        assert svc.authenticate_token(plain_token) is None


def test_authenticate_expired_token(app, owner):
    with app.app_context():
        t = svc.create_token('exp1', owner.id, ['bim:read'])
        # Setam expirat manual
        t.expires_at = datetime.utcnow() - timedelta(hours=1)
        db.session.commit()
        assert svc.authenticate_token(t.token) is None


def test_has_scope_wildcard(app, owner):
    with app.app_context():
        t = svc.create_token('wild', owner.id, ['*'])
        assert t.has_scope('anything') is True


def test_has_scope_exact(app, owner):
    with app.app_context():
        t = svc.create_token('exact', owner.id, ['bim:read', 'iot:read'])
        assert t.has_scope('bim:read') is True
        assert t.has_scope('iot:read') is True
        assert t.has_scope('bim:write') is False


def test_expires_days_sets_expires_at(app, owner):
    with app.app_context():
        t = svc.create_token('exp30', owner.id, ['bim:read'], expires_days=30)
        assert t.expires_at is not None
        delta = t.expires_at - datetime.utcnow()
        assert 29 * 24 * 3600 < delta.total_seconds() < 31 * 24 * 3600
