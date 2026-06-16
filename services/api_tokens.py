"""
API Tokens pentru autentificare publica (Faza 8).

CRUD + decorator @api_token_required pentru a proteja rute.
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional

from flask import request, jsonify, g

from models import db, ApiToken, Utilizator
from services import audit as audit_svc


_logger = logging.getLogger(__name__)


# ====================================================
# Rate-limit IN-MEMORY (Faza 5b)
#
# Fereastra fixa pe token_id: {token_id: (fereastra_start_epoch, contor)}.
# Single-worker pe PythonAnywhere -> structura locala procesului e suficienta
# (fara Redis). Gated pe flag-ul 'bim-api-rate-limit' (default OFF) ca sa nu
# schimbe comportamentul de azi si sa nu afecteze testele existente.
#
# Configurabil:
# - prin app.config: API_RATE_LIMIT (req/fereastra), API_RATE_LIMIT_WINDOW (sec)
# - fallback pe constantele de mai jos.
# Curatenie: cand dictionarul depaseste _MAX_INTRARI, eliminam ferestrele expirate
# (si, daca tot e plin, cele mai vechi - evictie LRU-aproximativa) ca sa marginim
# memoria pe un worker de lunga durata.
# ====================================================

DEFAULT_RATE_LIMIT = 120          # cereri permise per fereastra
DEFAULT_RATE_WINDOW = 60          # durata ferestrei in secunde
_MAX_INTRARI = 10000              # plafon intrari inainte de curatenie/evictie

# token_id -> [fereastra_start_epoch, contor]
_rate_state: dict[int, list] = {}
_rate_lock = threading.Lock()


def _rate_config() -> tuple[int, int]:
    """(limita, fereastra_sec) din app.config sau valorile implicite."""
    try:
        from flask import current_app
        limita = int(current_app.config.get('API_RATE_LIMIT', DEFAULT_RATE_LIMIT))
        fereastra = int(current_app.config.get('API_RATE_LIMIT_WINDOW', DEFAULT_RATE_WINDOW))
        return max(1, limita), max(1, fereastra)
    except Exception:
        return DEFAULT_RATE_LIMIT, DEFAULT_RATE_WINDOW


def _rate_limit_enabled() -> bool:
    """True cand flag-ul 'bim-api-rate-limit' e activ. Default OFF -> dezactivat."""
    try:
        from services import feature_flags as ff
        return ff.is_enabled('bim-api-rate-limit')
    except Exception:
        return False


def reset_rate_limit():
    """Goleste starea rate-limit. Folosit intre teste / la reload controlat."""
    with _rate_lock:
        _rate_state.clear()


def _curata_locked(now: float, fereastra: int):
    """Sub lock: elimina ferestrele expirate; daca tot e plin, evictie aproximativa."""
    expirate = [tid for tid, (start, _c) in _rate_state.items()
                if now - start >= fereastra]
    for tid in expirate:
        _rate_state.pop(tid, None)
    if len(_rate_state) > _MAX_INTRARI:
        # Evictie aproximativ-LRU: scoatem ferestrele cele mai vechi.
        ordonate = sorted(_rate_state.items(), key=lambda kv: kv[1][0])
        for tid, _ in ordonate[:len(_rate_state) - _MAX_INTRARI]:
            _rate_state.pop(tid, None)


def check_rate_limit(token_id: int) -> tuple[bool, int]:
    """
    Inregistreaza o cerere pentru `token_id` si verifica pragul.

    Returneaza (permis, retry_after_sec):
    - permis=True  -> sub prag (retry_after_sec=0).
    - permis=False -> prag depasit; retry_after_sec = secundele pana la
      resetarea ferestrei curente (>=1).

    No-op (mereu permis) cand flag-ul 'bim-api-rate-limit' e OFF."""
    if not _rate_limit_enabled():
        return True, 0

    limita, fereastra = _rate_config()
    now = time.time()
    with _rate_lock:
        if len(_rate_state) > _MAX_INTRARI:
            _curata_locked(now, fereastra)
        entry = _rate_state.get(token_id)
        if entry is None or now - entry[0] >= fereastra:
            # Fereastra noua
            _rate_state[token_id] = [now, 1]
            return True, 0
        # Fereastra in curs
        if entry[1] >= limita:
            retry_after = max(1, int(fereastra - (now - entry[0])) + 1)
            return False, retry_after
        entry[1] += 1
        return True, 0


def _raspuns_429(retry_after: int):
    """Raspuns 429 standard cu header Retry-After."""
    resp = jsonify({
        'error': 'rate limit exceeded',
        'retry_after': retry_after,
    })
    resp.status_code = 429
    resp.headers['Retry-After'] = str(retry_after)
    return resp


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
    # Tokenul e valid doar daca proprietarul mai exista si e activ. Asa,
    # dezactivarea/concedierea unui utilizator ii invalideaza imediat tokenurile
    # (fara revocare manuala) si evitam AttributeError pe owner orfan in rutele
    # care folosesc tok.owner pentru autorizare (ex. api_model_version_file).
    if not tok.owner or not getattr(tok.owner, 'activ', False):
        return None
    # Update last_used (best-effort, nu blocam la eroare)
    try:
        tok.last_used_at = datetime.utcnow()
        db.session.commit()
    except Exception:
        db.session.rollback()
    return tok


def _extract_token() -> Optional[str]:
    """
    Extrage tokenul din header-ul request-ului curent.
    Acceptam 'Authorization: Bearer <token>' sau 'X-Api-Token: <token>'.
    Returneaza None daca nu exista niciun header de token.
    """
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header[7:].strip() or None
    token = request.headers.get('X-Api-Token', '').strip()
    return token or None


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
            token = _extract_token()
            if not token:
                return jsonify({'error': 'missing token. Use Authorization: Bearer <token> or X-Api-Token header'}), 401

            tok = authenticate_token(token)
            if not tok:
                return jsonify({'error': 'invalid or expired token'}), 401

            # Rate-limit pe token (no-op cand flag-ul e OFF)
            permis, retry_after = check_rate_limit(tok.id)
            if not permis:
                return _raspuns_429(retry_after)

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


# ====================================================
# Dual-auth (sesiune SAU token)
# ====================================================

class DualAuthError(Exception):
    """Eroare de autentificare duala. Poarta un cod HTTP (401/403/429).

    Pentru 429 (rate-limit), retry_after poarta secundele pana la resetare,
    ca apelantul sa poata seta header-ul Retry-After."""

    def __init__(self, message: str, status: int = 401, retry_after: int = 0):
        super().__init__(message)
        self.message = message
        self.status = status
        self.retry_after = retry_after


def resolve_dual_auth(*required_scopes):
    """
    Rezolva autentificarea acceptand ORICARE dintre:
    1. Token API valid (header) cu toate scope-urile cerute -> seteaza g.api_token / g.api_user.
    2. Sesiune Flask-Login valida (utilizator logat).

    Folosita pe rute consumate atat programatic (token) cat si din front-end
    logat prin sesiune (ex. viewer federat). NU redirectioneaza la login;
    in schimb ridica DualAuthError cu status 401/403 (raspuns potrivit pt API).

    Returneaza tuple (sursa, utilizator):
    - ('token', Utilizator)   daca a fost validat prin token
    - ('sesiune', Utilizator) daca a fost validat prin sesiune

    Reguli:
    - Daca exista un header de token, are prioritate si trebuie sa fie valid
      + sa aiba scope-urile cerute (altfel 401/403). Asa evitam ca un token
      gresit sa "cada" silentios pe sesiune.
    - Altfel, daca user-ul e logat prin sesiune -> trece.
    - Altfel -> 401.
    """
    from flask_login import current_user

    token = _extract_token()
    if token:
        tok = authenticate_token(token)
        if not tok:
            raise DualAuthError('invalid or expired token', 401)
        # Rate-limit pe token (no-op cand flag-ul e OFF)
        permis, retry_after = check_rate_limit(tok.id)
        if not permis:
            raise DualAuthError('rate limit exceeded', 429, retry_after=retry_after)
        for required in required_scopes:
            if not tok.has_scope(required):
                raise DualAuthError(f'insufficient scope: {required}', 403)
        g.api_token = tok
        g.api_user = tok.owner
        return ('token', tok.owner)

    if current_user and current_user.is_authenticated:
        return ('sesiune', current_user)

    raise DualAuthError('autentificare necesara: sesiune sau token API', 401)
