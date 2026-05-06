"""
Serviciu de audit pentru entitatile BIM.

Strategie:
- API simplu `log(...)` pe care call-site-urile (rute, servicii) il apeleaza
  explicit la create / update / delete.
- Pentru update, helper `snapshot(obj, fields)` capteaza valorile inainte de
  modificare; comparam la final si stocam doar campurile modificate.
- Robust: orice eroare in audit (ex: tenant_id lipsa) e prinsa si nu blocheaza
  request-ul principal. Audit failures sunt LOGATE, nu propagate.

Folosire tipica intr-o ruta:

    from services.audit import log_create, log_update, log_delete, snapshot

    # CREATE
    s = Santier(...)
    db.session.add(s)
    db.session.flush()  # pentru a avea s.id
    log_create('santier', s.id, new_values={'cod': s.cod, 'nume': s.nume})
    db.session.commit()

    # UPDATE
    before = snapshot(s, ['cod', 'nume', 'adresa'])
    s.nume = request.form['nume']
    db.session.commit()
    log_update('santier', s.id, before, snapshot(s, ['cod', 'nume', 'adresa']))

    # DELETE
    log_delete('santier', s.id, old_values={'cod': s.cod, 'nume': s.nume})
    db.session.delete(s)
    db.session.commit()
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional

from models import db, AuditLog


_logger = logging.getLogger(__name__)


def _serialize(value: Any) -> Any:
    """Conversie sigura pentru JSON (date, datetime, Decimal, etc.)."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    try:
        from decimal import Decimal
        if isinstance(value, Decimal):
            return str(value)
    except Exception:
        pass
    return str(value)


def snapshot(obj: Any, fields: Iterable[str]) -> dict:
    """Captureaza valorile curente ale campurilor date pentru un obiect ORM."""
    result: dict = {}
    for f in fields:
        try:
            result[f] = _serialize(getattr(obj, f, None))
        except Exception:
            result[f] = None
    return result


def _diff(old: Mapping[str, Any], new: Mapping[str, Any]) -> tuple[dict, dict]:
    """Returneaza (old_changed, new_changed) - doar campurile cu valoare diferita."""
    old_changed: dict = {}
    new_changed: dict = {}
    keys = set(old.keys()) | set(new.keys())
    for k in keys:
        ov = old.get(k)
        nv = new.get(k)
        if ov != nv:
            old_changed[k] = ov
            new_changed[k] = nv
    return old_changed, new_changed


def _current_user_id() -> Optional[int]:
    """Returneaza id-ul user-ului curent, sau None daca nu suntem in request."""
    try:
        from flask_login import current_user
        if current_user and getattr(current_user, 'is_authenticated', False):
            return int(current_user.id)
    except Exception:
        pass
    return None


def _current_tenant_id() -> Optional[int]:
    """Returneaza tenant_id curent (din tenant.py) sau None."""
    try:
        import tenant as _tenant
        return _tenant.get_current_tenant_id()
    except Exception:
        return None


def _request_context() -> Optional[dict]:
    """Captureaza IP + user-agent + path daca suntem intr-un request."""
    try:
        from flask import request, has_request_context
        if not has_request_context():
            return None
        return {
            'ip': request.headers.get('X-Forwarded-For', request.remote_addr),
            'ua': (request.user_agent.string or '')[:200],
            'path': request.path,
            'method': request.method,
        }
    except Exception:
        return None


def log(
    action: str,
    entity_type: str,
    entity_id: Optional[int] = None,
    old_values: Optional[Mapping[str, Any]] = None,
    new_values: Optional[Mapping[str, Any]] = None,
    *,
    user_id: Optional[int] = None,
    tenant_id: Optional[int] = None,
    context: Optional[Mapping[str, Any]] = None,
    commit: bool = False,
) -> Optional[AuditLog]:
    """
    Inregistreaza o actiune in audit_log.

    Returneaza AuditLog creat (sau None daca a esuat). NU arunca exceptii -
    audit-ul nu trebuie sa rupa flow-ul principal.
    """
    try:
        if user_id is None:
            user_id = _current_user_id()
        if tenant_id is None:
            tenant_id = _current_tenant_id()
        if context is None:
            context = _request_context()

        entry = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            old_values_json=json.dumps(dict(old_values), ensure_ascii=False) if old_values else None,
            new_values_json=json.dumps(dict(new_values), ensure_ascii=False) if new_values else None,
            context_json=json.dumps(dict(context), ensure_ascii=False) if context else None,
            timestamp=datetime.utcnow(),
        )
        db.session.add(entry)
        if commit:
            db.session.commit()
        else:
            db.session.flush()
        return entry
    except Exception as e:
        _logger.warning('audit.log a esuat: %s', e, exc_info=False)
        try:
            db.session.rollback()
        except Exception:
            pass
        return None


def log_create(entity_type: str, entity_id: int, new_values: Optional[Mapping[str, Any]] = None, **kw):
    return log('create', entity_type, entity_id, new_values=new_values, **kw)


def log_update(
    entity_type: str,
    entity_id: int,
    old_values: Mapping[str, Any],
    new_values: Mapping[str, Any],
    **kw,
):
    """Logheaza un update doar daca exista campuri modificate."""
    old_changed, new_changed = _diff(old_values, new_values)
    if not new_changed:
        return None  # nimic modificat, skip
    return log('update', entity_type, entity_id,
               old_values=old_changed, new_values=new_changed, **kw)


def log_delete(entity_type: str, entity_id: int, old_values: Optional[Mapping[str, Any]] = None, **kw):
    return log('delete', entity_type, entity_id, old_values=old_values, **kw)
