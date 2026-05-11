"""
API Tokens pentru autentificare publica (Faza 8).

CRUD + decorator @api_token_required pentru a proteja rute.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional

from flask import request, jsonify, g

from models import db, ApiToken, Utilizator
from services import audit as audit_svc


_logger = logging.getLogger(__name__)


# ====================================================
# CRUD
# ====================================================

def _generate_token() -> str:
    return secrets.token_hex(32)


def create_token(nume: str, owner_id: int, scopes: list[str], *,
                 descriere: Optional[str] = None,
                 expires_days: Optional[int] = None,
                 tenant_id: Optional[int] = None,
                 commit: bool = True) -> ApiToken:
    """Creeaza un token nou. Returneaza obiectul cu token plain (afisat o singura data)."""
    if not nume or not nume.strip():
        raise ValueError('Numele tokenului e obligatoriu')
    # Validare scopes
    valid_scopes = {s[0] for s in ApiToken.SCOPES_DISPONIBILE} | {'*'}
    for s in scopes:
        if s not in valid_scopes:
            raise ValueError(f'Scope invalid: {s}')

    expires_at = None
    if expires_days is not None and expires_days > 0:
        expires_at = datetime.utcnow() + timedelta(days=expires_days)

    tok = ApiToken(
        tenant_id=tenant_id,
        token=_generate_token(),
        nume=nume.strip()[:150],
        descriere=(descriere or '').strip() or None,
        owner_id=owner_id,
        activ=True,
        expires_at=expires_at,
    )
    tok.scopes = scopes
    db.session.add(tok)
    db.session.flush()

    audit_svc.log_create('bim_api_token', tok.id, new_values={
        'nume': nume, 'owner_id': owner_id, 'scopes': scopes,
        'expires_days': expires_days,
    })
    if commit:
        db.session.commit()
    return tok


def revoke_token(tok: ApiToken, *, commit: bool = True):
    """Dezactiveaza un token (soft - prin activ=False)."""
    tok.activ = False
    audit_svc.log('revoke_api_token', 'bim_api_token', tok.id,
                  old_values={'activ': True}, new_values={'activ': False})
    if commit:
        db.session.commit()


# ====================================================
# Authentication
# ====================================================

def authenticate_token(token: str) -> Optional[ApiToken]:
    """
    Returneaza obiectul ApiToken daca tokenul e valid (activ, neexpirat).
    Actualizeaza last_used_at.
    """
    if not token or len(token) < 16:
        return None
    tok = ApiToken.query.filter_by(token=token, activ=True).first()
    if not tok:
        return None
    if tok.is_expired:
        return None
    # Update last_used (best-effort, nu blocam la eroare)
    try:
        tok.last_used_at = datetime.utcnow()
        db.session.commit()
    except Exception:
        db.session.rollback()
    return tok


def api_token_required(*required_scopes):
    """
    Decorator pentru a proteja o ruta cu autentificare API token.
    Token-ul vine prin header 'Authorization: Bearer <token>' sau
    'X-Api-Token: <token>'.

    Folosire:
        @api_token_required('bim:read')
        def my_endpoint():
            user = g.api_token.owner  # Utilizator object
            ...
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # Extragere token
            auth_header = request.headers.get('Authorization', '')
            token = None
            if auth_header.startswith('Bearer '):
                token = auth_header[7:].strip()
            else:
                token = request.headers.get('X-Api-Token', '').strip()
            if not token:
                return jsonify({'error': 'missing token. Use Authorization: Bearer <token> or X-Api-Token header'}), 401

            tok = authenticate_token(token)
            if not tok:
                return jsonify({'error': 'invalid or expired token'}), 401

            # Verificare scopes
            for required in required_scopes:
                if not tok.has_scope(required):
                    return jsonify({
                        'error': 'insufficient scope',
                        'required': required,
                        'available': tok.scopes,
                    }), 403

            # Inregistram in flask.g pentru folosire in handler
            g.api_token = tok
            g.api_user = tok.owner
            return f(*args, **kwargs)

        return wrapper
    return decorator
