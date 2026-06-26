"""Acces canonic tenant-safe pentru rute si servicii.

Acest modul este opt-in. Nu aplica filtre globale si nu inlocuieste inca
helperii existenti din `tenant.py`.
"""

from flask import abort, has_app_context, has_request_context
from flask_login import current_user
from sqlalchemy import or_

from tenant import MODE_OFF, MODE_OPTIONAL, MODE_STRICT


class TenantAccessError(Exception):
    """Eroare de baza pentru verificari tenant."""


class TenantScopeUnsupported(TenantAccessError):
    """Modelul nu are inca o regula directa de tenant scope."""


class TenantAccessDenied(TenantAccessError):
    """Obiectul cerut nu apartine tenantului curent."""


def get_tenant_mode():
    """Returneaza modul multi-tenant curent fara sa forteze request context."""
    if not has_app_context():
        return MODE_OFF

    try:
        from tenant import get_mode
        mod = get_mode()
    except RuntimeError:
        return MODE_OFF

    if mod in (MODE_OFF, MODE_OPTIONAL, MODE_STRICT):
        return mod
    return MODE_OFF


def get_current_tenant_id_safe():
    """Returneaza tenant_id curent sau None cand nu exista request context."""
    if not has_request_context():
        return None

    try:
        from tenant import get_current_tenant_id
        return _coerce_tenant_id(get_current_tenant_id())
    except RuntimeError:
        return None


def is_super_admin(user):
    """Admin fara tenant: poate opera explicit peste tenanturi in strict mode."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False

    este_admin = getattr(user, 'is_admin', False) or getattr(user, 'rol', None) == 'admin'
    return bool(este_admin and getattr(user, 'tenant_id', None) is None)


def model_has_tenant_id(model):
    """True daca modelul are coloana directa tenant_id."""
    return hasattr(model, 'tenant_id')


def query_for_tenant(model, tenant_id=None, include_global=False):
    """Construieste query tenant-safe pentru un model cu tenant_id direct.

    In mode off returneaza query-ul legacy nefiltrat. In optional filtreaza doar
    cand exista tenant_id. In strict inchide accesul pentru userii normali fara
    tenant si refuza modelele fara tenant_id direct.
    """
    query = model.query
    mod = get_tenant_mode()

    if mod == MODE_OFF:
        return query

    tenant_curent = _resolve_tenant_id(tenant_id)
    super_admin = _current_user_is_super_admin()

    if tenant_curent is None:
        if super_admin:
            return query
        if mod == MODE_OPTIONAL:
            return query
        if not model_has_tenant_id(model):
            raise TenantScopeUnsupported(_unsupported_message(model))
        return query.filter(False)

    if not model_has_tenant_id(model):
        raise TenantScopeUnsupported(_unsupported_message(model))

    if include_global:
        return query.filter(or_(model.tenant_id == tenant_curent, model.tenant_id.is_(None)))
    return query.filter(model.tenant_id == tenant_curent)


def get_or_404_for_tenant(model, object_id, tenant_id=None, include_global=False):
    """Returneaza obiectul vizibil tenantului curent sau 404.

    404 ascunde existenta obiectelor din alt tenant si pastreaza comportamentul
    familiar al rutelor Flask care folosesc `get_or_404`.
    """
    try:
        obiect = query_for_tenant(
            model,
            tenant_id=tenant_id,
            include_global=include_global,
        ).filter(model.id == object_id).first()
    except TenantScopeUnsupported:
        abort(404)

    if obiect is None:
        abort(404)
    return obiect


def ensure_same_tenant(obj, tenant_id=None, include_global=False):
    """Valideaza ca obiectul apartine tenantului curent si returneaza obiectul."""
    mod = get_tenant_mode()
    if mod == MODE_OFF:
        return obj

    model = obj.__class__
    tenant_curent = _resolve_tenant_id(tenant_id)

    if tenant_curent is None:
        if _current_user_is_super_admin():
            return obj
        if mod == MODE_OPTIONAL:
            return obj
        if not model_has_tenant_id(model):
            raise TenantScopeUnsupported(_unsupported_message(model))
        raise TenantAccessDenied('Tenant lipsa in strict mode.')

    if not model_has_tenant_id(model):
        raise TenantScopeUnsupported(_unsupported_message(model))

    tenant_obiect = _coerce_tenant_id(getattr(obj, 'tenant_id', None))
    if tenant_obiect == tenant_curent:
        return obj
    if include_global and tenant_obiect is None:
        return obj

    raise TenantAccessDenied('Obiectul nu apartine tenantului curent.')


def require_same_tenant(obj, tenant_id=None, include_global=False):
    """Wrapper pentru rute: abort daca obiectul nu este accesibil tenantului."""
    try:
        return ensure_same_tenant(
            obj,
            tenant_id=tenant_id,
            include_global=include_global,
        )
    except TenantScopeUnsupported:
        abort(404)
    except TenantAccessDenied:
        abort(404)


def get_project_or_404(project_id, tenant_id=None):
    """Lookup canonic pentru Proiect, pregatit pentru integrarea treptata."""
    from models import Proiect

    return get_or_404_for_tenant(Proiect, project_id, tenant_id=tenant_id)


def tenant_id_for_new_record_or_403():
    """Returneaza tenant_id pentru create in rute sau abort 403 in strict mode."""
    mod = get_tenant_mode()
    if mod == MODE_OFF:
        return None

    tenant_id = get_current_tenant_id_safe()
    if tenant_id is not None:
        return tenant_id

    if _current_user_is_super_admin():
        return None

    if mod == MODE_STRICT:
        abort(403, 'Nu exista tenant activ pentru creare in strict mode.')

    return None


def query_activities_for_tenant(tenant_id=None, include_global=False):
    """Query tenant-safe pentru RaportActivitate prin Proiect -> tenant_id."""
    from models import Angajat, Proiect, RaportActivitate

    query = RaportActivitate.query
    mod = get_tenant_mode()

    if mod == MODE_OFF:
        return query

    tenant_curent = _resolve_tenant_id(tenant_id)
    if tenant_curent is None:
        if _current_user_is_super_admin():
            return query
        if mod == MODE_OPTIONAL:
            return query
        return query.filter(False)

    if include_global:
        proiect_scope = or_(Proiect.tenant_id == tenant_curent, Proiect.tenant_id.is_(None))
    else:
        proiect_scope = Proiect.tenant_id == tenant_curent

    return query.filter(
        RaportActivitate.proiect.has(proiect_scope),
        RaportActivitate.angajat.has(or_(
            Angajat.tenant_id == tenant_curent,
            Angajat.tenant_id.is_(None),
        )),
    )


def get_activity_or_404(activity_id, tenant_id=None):
    """Returneaza RaportActivitate vizibil tenantului curent sau 404."""
    from models import RaportActivitate

    activitate = query_activities_for_tenant(tenant_id=tenant_id).filter(
        RaportActivitate.id == activity_id
    ).first()
    if activitate is None:
        abort(404)
    return activitate


def ensure_activity_same_tenant(activity, tenant_id=None):
    """Valideaza indirect RaportActivitate -> Proiect -> tenant_id."""
    mod = get_tenant_mode()
    if mod == MODE_OFF:
        return activity

    tenant_curent = _resolve_tenant_id(tenant_id)
    if tenant_curent is None:
        if _current_user_is_super_admin():
            return activity
        if mod == MODE_OPTIONAL:
            return activity
        raise TenantAccessDenied('Tenant lipsa in strict mode.')

    proiect = getattr(activity, 'proiect', None)
    proiect_tenant_id = _coerce_tenant_id(getattr(proiect, 'tenant_id', None))
    if proiect is None:
        angajat = getattr(activity, 'angajat', None)
        angajat_tenant_id = _coerce_tenant_id(getattr(angajat, 'tenant_id', None))
        if angajat_tenant_id == tenant_curent:
            return activity
        raise TenantAccessDenied('Activitatea nu are proiect tenant-scoped.')

    if proiect_tenant_id != tenant_curent:
        raise TenantAccessDenied('Proiectul activitatii nu apartine tenantului curent.')

    angajat = getattr(activity, 'angajat', None)
    angajat_tenant_id = _coerce_tenant_id(getattr(angajat, 'tenant_id', None))
    if angajat_tenant_id is not None and angajat_tenant_id != tenant_curent:
        raise TenantAccessDenied('Angajatul activitatii nu apartine tenantului curent.')

    return activity


def require_activity_same_tenant(activity, tenant_id=None):
    """Wrapper pentru rute: ascunde activitatile inaccesibile prin 404."""
    try:
        return ensure_activity_same_tenant(activity, tenant_id=tenant_id)
    except TenantAccessDenied:
        abort(404)


def ensure_activity_inputs_same_tenant(proiect_ids, angajat_ids=None, tenant_id=None):
    """Valideaza proiectele si angajatii selectati la creare/editare activitate."""
    mod = get_tenant_mode()
    if mod == MODE_OFF:
        return True

    tenant_curent = _resolve_tenant_id(tenant_id)
    if tenant_curent is None:
        if _current_user_is_super_admin():
            return True
        if mod == MODE_OPTIONAL:
            return True
        raise TenantAccessDenied('Tenant lipsa in strict mode.')

    from models import Angajat, Proiect

    proiect_ids_clean = _unique_positive_ints(proiect_ids)
    if not proiect_ids_clean:
        raise TenantAccessDenied('Activitatea trebuie sa aiba proiect tenant-scoped.')

    proiecte_ok = Proiect.query.filter(
        Proiect.id.in_(proiect_ids_clean),
        Proiect.tenant_id == tenant_curent,
    ).count()
    if proiecte_ok != len(proiect_ids_clean):
        raise TenantAccessDenied('Cel putin un proiect nu apartine tenantului curent.')

    angajat_ids_clean = _unique_positive_ints(angajat_ids or [])
    if angajat_ids_clean:
        angajati_ok = Angajat.query.filter(
            Angajat.id.in_(angajat_ids_clean),
            or_(Angajat.tenant_id == tenant_curent, Angajat.tenant_id.is_(None)),
        ).count()
        if angajati_ok != len(angajat_ids_clean):
            raise TenantAccessDenied('Cel putin un angajat nu apartine tenantului curent.')

    return True


def require_activity_inputs_same_tenant(proiect_ids, angajat_ids=None, tenant_id=None):
    """Wrapper pentru rute create/edit: abort daca formularul amesteca tenanturi."""
    try:
        return ensure_activity_inputs_same_tenant(
            proiect_ids,
            angajat_ids=angajat_ids,
            tenant_id=tenant_id,
        )
    except TenantAccessDenied:
        abort(404)


def _resolve_tenant_id(tenant_id):
    if tenant_id is not None:
        return _coerce_tenant_id(tenant_id)
    return get_current_tenant_id_safe()


def _coerce_tenant_id(tenant_id):
    if tenant_id is None:
        return None
    try:
        return int(tenant_id)
    except (TypeError, ValueError):
        return None


def _unique_positive_ints(values):
    rezultat = []
    for value in values:
        try:
            int_value = int(value)
        except (TypeError, ValueError):
            continue
        if int_value > 0 and int_value not in rezultat:
            rezultat.append(int_value)
    return rezultat


def _current_user_is_super_admin():
    if not has_request_context():
        return False
    try:
        return is_super_admin(current_user)
    except RuntimeError:
        return False


def _unsupported_message(model):
    nume_model = getattr(model, '__name__', str(model))
    return f'{nume_model} nu are tenant_id direct. Scope-ul indirect se adauga intr-un PR separat.'
