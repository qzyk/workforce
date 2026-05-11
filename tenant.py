"""
Multi-tenant infrastructure.

Modul de operare (config flag MULTI_TENANT_MODE):
- 'off' (default)        - mod single-tenant. Toate query-urile ignora tenant_id.
- 'optional'             - tenant_id e populat daca exista, dar nu se filtreaza fortat.
                           Tipic pentru migration period.
- 'strict'               - filter automat pe tenant_id. Cross-tenant access prohibit.

Tenant detection sources (in ordine):
1. flask.g.tenant_override (set programatic, ex. test fixture)
2. session['tenant_id']
3. current_user.tenant_id (din DB)
4. subdomain (ex: edifico.workforce.app -> tenant cod 'edifico')
5. None (si MODE=off, e ok)

Decoratori:
- @tenant_required          forteaza prezenta unui tenant in request
- @tenant_admin_required    cere ca user-ul sa fie admin in tenant-ul curent

Helpers:
- get_current_tenant_id() -> int|None
- with_tenant_scope(query, model) -> query filtered by current tenant
- TenantQueryMixin (model mixin)
"""

from functools import wraps
from flask import g, session, current_app, request, redirect, url_for, abort
from flask_login import current_user


# Modurile suportate
MODE_OFF = 'off'
MODE_OPTIONAL = 'optional'
MODE_STRICT = 'strict'

DEFAULT_MODE = MODE_OFF


def get_mode():
    """Returneaza modul curent multi-tenant din config."""
    return current_app.config.get('MULTI_TENANT_MODE', DEFAULT_MODE)


def get_current_tenant_id():
    """
    Returneaza ID-ul tenant-ului curent (int) sau None.
    Se cache-uiaza pe flask.g pentru request-ul curent.
    """
    if hasattr(g, '_tenant_id_cached'):
        return g._tenant_id_cached

    tenant_id = None

    # 1. Override programatic (folosit in teste si CLI)
    if hasattr(g, 'tenant_override'):
        tenant_id = g.tenant_override
    # 2. Session
    elif 'tenant_id' in session:
        tenant_id = session.get('tenant_id')
    # 3. User logged in
    elif current_user and current_user.is_authenticated:
        tenant_id = getattr(current_user, 'tenant_id', None)
    # 4. Subdomain (dezactivat by default - opt-in via config)
    elif current_app.config.get('TENANT_FROM_SUBDOMAIN', False):
        tenant_id = _resolve_tenant_from_subdomain()

    # Convert to int if string
    if tenant_id is not None:
        try:
            tenant_id = int(tenant_id)
        except (ValueError, TypeError):
            tenant_id = None

    g._tenant_id_cached = tenant_id
    return tenant_id


def get_current_tenant():
    """Returneaza obiectul Tenant curent (lazy-loaded) sau None."""
    tid = get_current_tenant_id()
    if tid is None:
        return None
    if hasattr(g, '_tenant_obj_cached') and g._tenant_obj_cached.id == tid:
        return g._tenant_obj_cached
    from models import Tenant
    t = Tenant.query.get(tid)
    g._tenant_obj_cached = t
    return t


def _resolve_tenant_from_subdomain():
    """
    Mapping subdomain -> tenant_id.
    Ex: edifico.workforce.app -> Tenant(cod='edifico').id
    """
    host = request.host.split(':')[0]
    parts = host.split('.')
    if len(parts) < 3:
        return None
    subdomain = parts[0]
    if subdomain in ('www', 'app', 'workforce'):
        return None
    from models import Tenant
    t = Tenant.query.filter_by(cod=subdomain).first()
    return t.id if t else None


def with_tenant_scope(query, model):
    """
    Aplica filter tenant pe un query, daca MODE=strict si user-ul e tenant-scoped.

    Usage:
        from tenant import with_tenant_scope
        from models import Proiect
        proiecte = with_tenant_scope(Proiect.query, Proiect).all()
    """
    if get_mode() != MODE_STRICT:
        return query

    tenant_id = get_current_tenant_id()
    if tenant_id is None:
        # MODE=strict si nu avem tenant -> nu returnam nimic (cu exceptia super-admin)
        if current_user and current_user.is_authenticated and current_user.rol == 'admin' \
                and getattr(current_user, 'tenant_id', None) is None:
            # Super-admin (admin fara tenant) vede tot
            return query
        return query.filter(False)

    if hasattr(model, 'tenant_id'):
        return query.filter(model.tenant_id == tenant_id)
    return query


# ============================================================
# DECORATORI
# ============================================================

def tenant_required(view_func):
    """Decorator care impune existenta unui tenant in request."""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if get_mode() == MODE_OFF:
            return view_func(*args, **kwargs)
        if get_current_tenant_id() is None:
            abort(403, 'Acest endpoint cere un tenant activ.')
        return view_func(*args, **kwargs)
    return wrapper


def tenant_admin_required(view_func):
    """User-ul trebuie sa fie admin in tenant-ul curent (sau super-admin)."""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not current_user.is_admin:
            abort(403)
        if get_mode() == MODE_STRICT:
            tid = get_current_tenant_id()
            if tid is not None and getattr(current_user, 'tenant_id', None) not in (None, tid):
                abort(403, 'Cross-tenant admin access blocat.')
        return view_func(*args, **kwargs)
    return wrapper


# ============================================================
# CONTEXT PROCESSOR (pentru template-uri)
# ============================================================

def init_app(app):
    """Inregistreaza middleware + context processor pentru tenant."""
    @app.before_request
    def _tenant_before_request():
        # Curat cache-ul per request
        if hasattr(g, '_tenant_id_cached'):
            del g._tenant_id_cached
        if hasattr(g, '_tenant_obj_cached'):
            del g._tenant_obj_cached

    @app.context_processor
    def inject_tenant():
        try:
            return {
                'current_tenant': get_current_tenant(),
                'current_tenant_id': get_current_tenant_id(),
                'multi_tenant_mode': get_mode(),
            }
        except Exception:
            return {
                'current_tenant': None,
                'current_tenant_id': None,
                'multi_tenant_mode': MODE_OFF,
            }
