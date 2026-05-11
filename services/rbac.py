"""
RBAC fin pe scope BIM (Faza 8).

Verifica daca un user are dreptul sa execute o actiune pe un scope dat
(santier/cladire/disciplina/global).

Conform ISO 19650:
- information_manager: full pe proiect (publish, archive, manage tokens)
- lead_designer: publish/share per disciplina
- task_team_manager: WIP/shared management pe disciplina lor
- reviewer: read-only pe published
- viewer: read-only general
- cost_manager: edit 5D cost
- iot_operator: ingest senzori (token-based recomandat)

Permisiunile sunt 'actiune:scope', ex: 'publish:disciplina'.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from models import db, BIMRoleAssignment
from services import audit as audit_svc


_logger = logging.getLogger(__name__)


# ====================================================
# Permission matrix
# Mapeaza rol -> set de actiuni pe care le poate face
# ====================================================
ROLE_PERMISSIONS = {
    'information_manager': {
        'bim:read', 'bim:write',
        'version:publish', 'version:archive', 'version:reject',
        'rule:run', 'clash:run',
        'cost:read', 'cost:write',
        'schedule:read', 'schedule:write',
        'iot:read', 'iot:write',
        'token:manage',
    },
    'lead_designer': {
        'bim:read', 'bim:write',
        'version:share', 'version:publish',
        'rule:run', 'clash:run',
        'cost:read',
        'schedule:read',
        'iot:read',
    },
    'task_team_manager': {
        'bim:read', 'bim:write',
        'version:share',
        'rule:run',
        'cost:read',
        'schedule:read', 'schedule:write',
    },
    'reviewer': {
        'bim:read',
        'cost:read', 'schedule:read', 'iot:read',
    },
    'viewer': {
        'bim:read',
    },
    'cost_manager': {
        'bim:read',
        'cost:read', 'cost:write',
        'schedule:read',
    },
    'iot_operator': {
        'iot:read', 'iot:write',
    },
}


# ====================================================
# Permission check
# ====================================================

def has_permission(user, action: str, *,
                   santier_id: Optional[int] = None,
                   cladire_id: Optional[int] = None,
                   disciplina: Optional[str] = None,
                   proiect_id: Optional[int] = None,
                   today=None) -> bool:
    """
    Returneaza True daca user-ul are permisiunea pe scope-ul dat.

    Strategie:
    1. Admin tenant (Utilizator.rol == 'admin') -> orice
    2. Cautam role assignments active:
       - global cu rol care contine 'action'
       - sau scope_type matching cu scope_id matching (sau scope_disciplina)
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False

    # Admin global pe tenant bypaseaza orice
    if getattr(user, 'rol', None) == 'admin':
        return True

    today = today or date.today()

    assignments = (BIMRoleAssignment.query
                   .filter_by(user_id=user.id, activ=True)
                   .all())

    for asgn in assignments:
        if not asgn.is_in_force(today):
            continue
        allowed = ROLE_PERMISSIONS.get(asgn.rol, set())
        if action not in allowed:
            continue
        # Verificam scope
        if asgn.scope_type == 'global':
            return True
        if asgn.scope_type == 'proiect' and proiect_id == asgn.scope_id:
            return True
        if asgn.scope_type == 'santier' and santier_id == asgn.scope_id:
            return True
        if asgn.scope_type == 'cladire' and cladire_id == asgn.scope_id:
            return True
        if asgn.scope_type == 'disciplina' and disciplina and \
                disciplina.upper() == (asgn.scope_disciplina or '').upper():
            return True

    return False


# ====================================================
# CRUD asignari
# ====================================================

def assign_role(user_id: int, rol: str, *,
                scope_type: str = 'global',
                scope_id: Optional[int] = None,
                scope_disciplina: Optional[str] = None,
                data_start=None,
                data_sfarsit=None,
                created_by=None,
                tenant_id: Optional[int] = None,
                commit: bool = True) -> BIMRoleAssignment:
    """Creeaza o asignare de rol."""
    if rol not in ROLE_PERMISSIONS:
        raise ValueError(f'Rol necunoscut: {rol} (valori: {sorted(ROLE_PERMISSIONS.keys())})')
    if scope_type not in ('global', 'proiect', 'santier', 'cladire', 'disciplina'):
        raise ValueError(f'scope_type invalid: {scope_type}')

    asgn = BIMRoleAssignment(
        tenant_id=tenant_id,
        user_id=user_id,
        rol=rol,
        scope_type=scope_type,
        scope_id=scope_id,
        scope_disciplina=(scope_disciplina or '').upper() or None,
        data_start=data_start,
        data_sfarsit=data_sfarsit,
        activ=True,
        creat_de_id=getattr(created_by, 'id', None) if created_by else None,
    )
    db.session.add(asgn)
    db.session.flush()

    audit_svc.log_create('bim_role_assignment', asgn.id, new_values={
        'user_id': user_id, 'rol': rol,
        'scope_type': scope_type, 'scope_id': scope_id,
        'scope_disciplina': asgn.scope_disciplina,
    })
    if commit:
        db.session.commit()
    return asgn


def revoke_role(asgn: BIMRoleAssignment, *, user=None, commit: bool = True):
    """Dezactiveaza o asignare (soft delete via activ=False)."""
    asgn.activ = False
    audit_svc.log('revoke_role', 'bim_role_assignment', asgn.id,
                  old_values={'activ': True}, new_values={'activ': False})
    if commit:
        db.session.commit()


def get_user_roles(user_id: int, *, only_active: bool = True) -> list[BIMRoleAssignment]:
    q = BIMRoleAssignment.query.filter_by(user_id=user_id)
    if only_active:
        q = q.filter_by(activ=True)
    return q.order_by(BIMRoleAssignment.data_creare.desc()).all()
