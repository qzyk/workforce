"""Acces canonic tenant-safe pentru rute si servicii.

Acest modul este opt-in. Nu aplica filtre globale si nu inlocuieste inca
helperii existenti din `tenant.py`.
"""

from flask import abort, has_app_context, has_request_context
from flask_login import current_user
from sqlalchemy import and_, or_

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


def query_timesheets_for_tenant(tenant_id=None, include_global=False):
    """Query tenant-safe pentru Pontaj prin Proiect -> tenant_id."""
    from models import Angajat, Pontaj, Proiect

    query = Pontaj.query
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
        Pontaj.proiect.has(proiect_scope),
        Pontaj.angajat.has(or_(
            Angajat.tenant_id == tenant_curent,
            Angajat.tenant_id.is_(None),
        )),
    )


def get_timesheet_or_404(timesheet_id, tenant_id=None):
    """Returneaza Pontaj vizibil tenantului curent sau 404."""
    from models import Pontaj

    pontaj = query_timesheets_for_tenant(tenant_id=tenant_id).filter(
        Pontaj.id == timesheet_id
    ).first()
    if pontaj is None:
        abort(404)
    return pontaj


def ensure_timesheet_same_tenant(timesheet, tenant_id=None):
    """Valideaza indirect Pontaj -> Proiect -> tenant_id."""
    mod = get_tenant_mode()
    if mod == MODE_OFF:
        return timesheet

    tenant_curent = _resolve_tenant_id(tenant_id)
    if tenant_curent is None:
        if _current_user_is_super_admin():
            return timesheet
        if mod == MODE_OPTIONAL:
            return timesheet
        raise TenantAccessDenied('Tenant lipsa in strict mode.')

    proiect = getattr(timesheet, 'proiect', None)
    proiect_tenant_id = _coerce_tenant_id(getattr(proiect, 'tenant_id', None))
    if proiect is None:
        angajat = getattr(timesheet, 'angajat', None)
        angajat_tenant_id = _coerce_tenant_id(getattr(angajat, 'tenant_id', None))
        if angajat_tenant_id == tenant_curent:
            return timesheet
        raise TenantAccessDenied('Pontajul nu are proiect tenant-scoped.')

    if proiect_tenant_id != tenant_curent:
        raise TenantAccessDenied('Proiectul pontajului nu apartine tenantului curent.')

    angajat = getattr(timesheet, 'angajat', None)
    angajat_tenant_id = _coerce_tenant_id(getattr(angajat, 'tenant_id', None))
    if angajat_tenant_id is not None and angajat_tenant_id != tenant_curent:
        raise TenantAccessDenied('Angajatul pontajului nu apartine tenantului curent.')

    return timesheet


def require_timesheet_same_tenant(timesheet, tenant_id=None):
    """Wrapper pentru rute: ascunde pontajele inaccesibile prin 404."""
    try:
        return ensure_timesheet_same_tenant(timesheet, tenant_id=tenant_id)
    except TenantAccessDenied:
        abort(404)


def ensure_timesheet_inputs_same_tenant(proiect_id=None, angajat_id=None, tenant_id=None):
    """Valideaza proiectul si angajatul selectati la creare/editare pontaj."""
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

    proiect_ids = _unique_positive_ints([proiect_id] if proiect_id is not None else [])
    if proiect_ids:
        proiect_ok = Proiect.query.filter(
            Proiect.id == proiect_ids[0],
            Proiect.tenant_id == tenant_curent,
        ).first()
        if proiect_ok is None:
            raise TenantAccessDenied('Proiectul pontajului nu apartine tenantului curent.')

    angajat_ids = _unique_positive_ints([angajat_id] if angajat_id is not None else [])
    if angajat_ids:
        angajat_ok = Angajat.query.filter(
            Angajat.id == angajat_ids[0],
            or_(Angajat.tenant_id == tenant_curent, Angajat.tenant_id.is_(None)),
        ).first()
        if angajat_ok is None:
            raise TenantAccessDenied('Angajatul pontajului nu apartine tenantului curent.')

    return True


def require_timesheet_inputs_same_tenant(proiect_id=None, angajat_id=None, tenant_id=None):
    """Wrapper pentru rute create/edit: abort daca formularul amesteca tenanturi."""
    try:
        return ensure_timesheet_inputs_same_tenant(
            proiect_id=proiect_id,
            angajat_id=angajat_id,
            tenant_id=tenant_id,
        )
    except TenantAccessDenied:
        abort(404)


def query_contracts_for_tenant(tenant_id=None, include_global=False):
    """Query tenant-safe pentru Contract."""
    from models import Contract

    return query_for_tenant(
        Contract,
        tenant_id=tenant_id,
        include_global=include_global,
    )


def get_contract_or_404(contract_id, tenant_id=None):
    """Returneaza Contract vizibil tenantului curent sau 404."""
    from models import Contract

    return get_or_404_for_tenant(Contract, contract_id, tenant_id=tenant_id)


def ensure_contract_same_tenant(contract, tenant_id=None):
    """Valideaza ca un Contract apartine tenantului curent."""
    return ensure_same_tenant(contract, tenant_id=tenant_id)


def require_contract_same_tenant(contract, tenant_id=None):
    """Wrapper pentru rute: ascunde contractele inaccesibile prin 404."""
    return require_same_tenant(contract, tenant_id=tenant_id)


def get_program_referinta_or_404(program_id, tenant_id=None):
    """Returneaza ProgramReferinta vizibil tenantului curent sau 404."""
    from models import ProgramReferinta

    return get_or_404_for_tenant(ProgramReferinta, program_id, tenant_id=tenant_id)


def get_task_program_or_404(task_id, tenant_id=None):
    """Returneaza TaskProgram vizibil tenantului curent sau 404."""
    from models import TaskProgram

    return get_or_404_for_tenant(TaskProgram, task_id, tenant_id=tenant_id)


def get_oferta_contract_or_404(oferta_id, tenant_id=None):
    """Returneaza OfertaContract vizibila tenantului curent sau 404."""
    from models import OfertaContract

    return get_or_404_for_tenant(OfertaContract, oferta_id, tenant_id=tenant_id)


def get_pozitie_boq_or_404(pozitie_id, tenant_id=None):
    """Returneaza PozitieBoQ vizibila tenantului curent sau 404."""
    from models import PozitieBoQ

    return get_or_404_for_tenant(PozitieBoQ, pozitie_id, tenant_id=tenant_id)


def get_situatie_lunara_or_404(situatie_id, tenant_id=None):
    """Returneaza SituatieLunara vizibila tenantului curent sau 404."""
    from models import SituatieLunara

    return get_or_404_for_tenant(SituatieLunara, situatie_id, tenant_id=tenant_id)


def get_revendicare_or_404(revendicare_id, tenant_id=None):
    """Returneaza Revendicare vizibila tenantului curent sau 404."""
    from models import Revendicare

    return get_or_404_for_tenant(Revendicare, revendicare_id, tenant_id=tenant_id)


def get_revendicare_termen_or_404(link_id, tenant_id=None):
    """Returneaza link RevendicareTermen vizibil tenantului curent sau 404."""
    from models import RevendicareTermen

    return get_or_404_for_tenant(RevendicareTermen, link_id, tenant_id=tenant_id)


def get_revendicare_task_or_404(link_id, tenant_id=None):
    """Returneaza link RevendicareTask vizibil tenantului curent sau 404."""
    from models import RevendicareTask

    return get_or_404_for_tenant(RevendicareTask, link_id, tenant_id=tenant_id)


def get_revendicare_cantitate_or_404(link_id, tenant_id=None):
    """Returneaza link RevendicareCantitate vizibil tenantului curent sau 404."""
    from models import RevendicareCantitate

    return get_or_404_for_tenant(RevendicareCantitate, link_id, tenant_id=tenant_id)


def get_termen_contract_or_404(termen_id, tenant_id=None):
    """Returneaza TermenContract vizibil tenantului curent sau 404."""
    from models import TermenContract

    return get_or_404_for_tenant(TermenContract, termen_id, tenant_id=tenant_id)


def get_cantitate_executata_lunara_or_404(cantitate_id, tenant_id=None):
    """Returneaza CantitateExecutataLunara vizibila tenantului curent sau 404."""
    from models import CantitateExecutataLunara

    return get_or_404_for_tenant(
        CantitateExecutataLunara,
        cantitate_id,
        tenant_id=tenant_id,
    )


def get_proces_verbal_or_404(proces_verbal_id, tenant_id=None):
    """Returneaza ProcesVerbal vizibil tenantului curent sau 404."""
    from models import ProcesVerbal

    return get_or_404_for_tenant(ProcesVerbal, proces_verbal_id, tenant_id=tenant_id)


def get_raport_lucrari_proiect_or_404(raport_id, tenant_id=None):
    """Returneaza RaportLucrariProiect vizibil tenantului curent sau 404."""
    from models import RaportLucrariProiect

    return get_or_404_for_tenant(
        RaportLucrariProiect,
        raport_id,
        tenant_id=tenant_id,
    )


def get_corespondenta_or_404(corespondenta_id, tenant_id=None):
    """Returneaza Corespondenta vizibila tenantului curent sau 404."""
    from models import Corespondenta

    return get_or_404_for_tenant(Corespondenta, corespondenta_id, tenant_id=tenant_id)


def get_regula_notificare_or_404(regula_id, tenant_id=None):
    """Returneaza ReguliNotificareProiect vizibila tenantului curent sau 404."""
    from models import ReguliNotificareProiect

    return get_or_404_for_tenant(
        ReguliNotificareProiect,
        regula_id,
        tenant_id=tenant_id,
    )


def query_tarife_categorie_for_tenant(tenant_id=None, include_global_defaults=False):
    """Query tenant-safe pentru TarifCategorie.

    `include_global_defaults=True` include doar tarifele globale
    `tenant_id=NULL`, folosite ca seed/catalog default. Override-urile de proiect
    raman filtrate prin `tenant_id` si prin ruta care valideaza proiectul.
    """
    from models import TarifCategorie

    return query_for_tenant(
        TarifCategorie,
        tenant_id=tenant_id,
        include_global=include_global_defaults,
    )


def query_gantt_plans_for_tenant(tenant_id=None, include_global=False):
    """Query tenant-safe pentru planuri Gantt salvate.

    Planurile operationale nu devin globale doar pentru ca au `tenant_id=NULL`.
    In modurile scoped sunt vizibile prin `tenant_id` direct sau prin proiectul
    parinte. `include_global=True` este rezervat doar compatibilitatii explicite
    cu randuri vechi fara proiect si fara tenant.
    """
    from models import GanttPlan, Proiect, db

    query = GanttPlan.query
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

    proiect_scope = Proiect.tenant_id == tenant_curent
    direct_scope = and_(
        GanttPlan.tenant_id == tenant_curent,
        or_(
            GanttPlan.proiect_id.is_(None),
            GanttPlan.proiect.has(proiect_scope),
        ),
    )
    inherited_scope = and_(
        GanttPlan.tenant_id.is_(None),
        GanttPlan.proiect.has(proiect_scope),
    )
    scope = or_(direct_scope, inherited_scope)
    if include_global:
        scope = or_(
            scope,
            and_(GanttPlan.tenant_id.is_(None), GanttPlan.proiect_id.is_(None)),
        )
    return query.filter(scope)


def get_gantt_plan_or_404(plan_id, tenant_id=None, include_global=False):
    """Returneaza GanttPlan vizibil tenantului curent sau 404."""
    from models import GanttPlan

    plan = query_gantt_plans_for_tenant(
        tenant_id=tenant_id,
        include_global=include_global,
    ).filter(GanttPlan.id == plan_id).first()
    if plan is None:
        abort(404)
    return plan


def ensure_gantt_plan_same_tenant(plan, tenant_id=None, include_global=False):
    """Valideaza GanttPlan prin tenant_id direct si/sau Proiect."""
    mod = get_tenant_mode()
    if mod == MODE_OFF:
        return plan

    tenant_curent = _resolve_tenant_id(tenant_id)
    if tenant_curent is None:
        if _current_user_is_super_admin():
            return plan
        if mod == MODE_OPTIONAL:
            return plan
        raise TenantAccessDenied('Tenant lipsa in strict mode.')

    tenant_plan = _coerce_tenant_id(getattr(plan, 'tenant_id', None))
    proiect = getattr(plan, 'proiect', None)
    proiect_id = getattr(plan, 'proiect_id', None)
    tenant_proiect = _coerce_tenant_id(getattr(proiect, 'tenant_id', None))

    if tenant_plan is not None and tenant_plan != tenant_curent:
        raise TenantAccessDenied('Planul Gantt nu apartine tenantului curent.')

    if proiect_id is not None and tenant_proiect != tenant_curent:
        raise TenantAccessDenied('Proiectul planului Gantt nu apartine tenantului curent.')

    if tenant_plan == tenant_curent:
        return plan

    if proiect_id is not None and tenant_proiect == tenant_curent:
        return plan

    if include_global and tenant_plan is None and proiect_id is None:
        return plan

    raise TenantAccessDenied('Planul Gantt nu are owner tenant-safe.')


def require_gantt_plan_same_tenant(plan, tenant_id=None, include_global=False):
    """Wrapper pentru rute: ascunde planurile Gantt inaccesibile prin 404."""
    try:
        return ensure_gantt_plan_same_tenant(
            plan,
            tenant_id=tenant_id,
            include_global=include_global,
        )
    except TenantAccessDenied:
        abort(404)


def query_gantt_wbs_nodes_for_tenant(plan_id=None, tenant_id=None):
    """Query tenant-safe pentru noduri WBS prin GanttPlan."""
    from models import GanttPlan, GanttWbsNod

    query = GanttWbsNod.query
    mod = get_tenant_mode()
    if mod == MODE_OFF:
        return query.filter_by(plan_id=plan_id) if plan_id is not None else query

    tenant_curent = _resolve_tenant_id(tenant_id)
    if tenant_curent is None:
        if _current_user_is_super_admin():
            return query.filter_by(plan_id=plan_id) if plan_id is not None else query
        if mod == MODE_OPTIONAL:
            return query.filter_by(plan_id=plan_id) if plan_id is not None else query
        return query.filter(False)

    plan_ids = query_gantt_plans_for_tenant(
        tenant_id=tenant_curent,
    ).with_entities(GanttPlan.id)
    query = query.filter(
        GanttWbsNod.plan_id.in_(plan_ids),
        or_(
            GanttWbsNod.tenant_id == tenant_curent,
            GanttWbsNod.tenant_id.is_(None),
        ),
    )
    if plan_id is not None:
        query = query.filter(GanttWbsNod.plan_id == plan_id)
    return query


def get_gantt_wbs_node_or_404(node_id, tenant_id=None):
    """Returneaza GanttWbsNod vizibil tenantului curent sau 404."""
    from models import GanttWbsNod

    nod = query_gantt_wbs_nodes_for_tenant(tenant_id=tenant_id).filter(
        GanttWbsNod.id == node_id
    ).first()
    if nod is None:
        abort(404)
    return nod


def ensure_gantt_inputs_same_tenant(proiect_id=None, plan_id=None, tenant_id=None):
    """Valideaza proiectul si planul selectate in fluxurile Gantt."""
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

    from models import GanttPlan, Proiect

    proiect_ids = _unique_positive_ints([proiect_id] if proiect_id is not None else [])
    proiect_ok = None
    if proiect_ids:
        proiect_ok = Proiect.query.filter(
            Proiect.id == proiect_ids[0],
            Proiect.tenant_id == tenant_curent,
        ).first()
        if proiect_ok is None:
            raise TenantAccessDenied('Proiectul Gantt nu apartine tenantului curent.')

    plan_ids = _unique_positive_ints([plan_id] if plan_id is not None else [])
    if plan_ids:
        plan = db.session.get(GanttPlan, plan_ids[0])
        if plan is None:
            raise TenantAccessDenied('Planul Gantt nu exista.')
        ensure_gantt_plan_same_tenant(plan, tenant_id=tenant_curent)
        if proiect_ok is not None and getattr(plan, 'proiect_id', None):
            if plan.proiect_id != proiect_ok.id:
                raise TenantAccessDenied('Planul Gantt nu apartine proiectului selectat.')

    return True


def require_gantt_inputs_same_tenant(proiect_id=None, plan_id=None, tenant_id=None):
    """Wrapper pentru rute create/edit: abort daca inputurile amesteca tenanturi."""
    try:
        return ensure_gantt_inputs_same_tenant(
            proiect_id=proiect_id,
            plan_id=plan_id,
            tenant_id=tenant_id,
        )
    except TenantAccessDenied:
        abort(404)


def query_gantt_profiles_for_tenant(tenant_id=None, include_global=True):
    """Query tenant-safe pentru profiluri de mapare Gantt."""
    from models import GanttProfilMapare

    return query_for_tenant(
        GanttProfilMapare,
        tenant_id=tenant_id,
        include_global=include_global,
    )


def query_gantt_synonyms_for_tenant(tenant_id=None, include_global=True):
    """Query tenant-safe pentru sinonime de coloane Gantt."""
    from models import GanttSinonimColoana

    return query_for_tenant(
        GanttSinonimColoana,
        tenant_id=tenant_id,
        include_global=include_global,
    )


def query_gantt_classification_rules_for_tenant(tenant_id=None, include_global=True):
    """Query tenant-safe pentru reguli de clasificare Gantt."""
    from models import GanttClasificareRegula

    return query_for_tenant(
        GanttClasificareRegula,
        tenant_id=tenant_id,
        include_global=include_global,
    )


def query_gantt_relation_templates_for_tenant(tenant_id=None, include_global=True):
    """Query tenant-safe pentru template-uri de relatii Gantt."""
    from models import GanttRelatieTemplate

    return query_for_tenant(
        GanttRelatieTemplate,
        tenant_id=tenant_id,
        include_global=include_global,
    )


def query_project_documents_for_tenant(tenant_id=None, include_global=False):
    """Query tenant-safe pentru DocumentProiect prin Proiect -> tenant_id."""
    from models import DocumentProiect, Proiect

    query = DocumentProiect.query
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

    proiect_scope = Proiect.tenant_id == tenant_curent
    if include_global:
        proiect_scope = or_(proiect_scope, Proiect.tenant_id.is_(None))

    return query.filter(DocumentProiect.proiect.has(proiect_scope))


def get_project_document_or_404(document_id, tenant_id=None):
    """Returneaza DocumentProiect vizibil tenantului curent sau 404."""
    from models import DocumentProiect

    document = query_project_documents_for_tenant(tenant_id=tenant_id).filter(
        DocumentProiect.id == document_id
    ).first()
    if document is None:
        abort(404)
    return document


def query_project_document_revisions_for_tenant(tenant_id=None, include_global=False):
    """Query tenant-safe pentru RevizieDocument prin documentul/proiectul parinte."""
    from models import DocumentProiect, Proiect, RevizieDocument

    query = RevizieDocument.query
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

    proiect_scope = Proiect.tenant_id == tenant_curent
    if include_global:
        proiect_scope = or_(proiect_scope, Proiect.tenant_id.is_(None))

    return query.filter(
        RevizieDocument.document_proiect.has(
            DocumentProiect.proiect.has(proiect_scope)
        )
    )


def get_project_document_revision_or_404(revision_id, tenant_id=None):
    """Returneaza RevizieDocument vizibila tenantului curent sau 404."""
    from models import RevizieDocument

    revision = query_project_document_revisions_for_tenant(
        tenant_id=tenant_id
    ).filter(RevizieDocument.id == revision_id).first()
    if revision is None:
        abort(404)
    return revision


def ensure_project_document_same_tenant(document, tenant_id=None):
    """Valideaza DocumentProiect -> Proiect -> tenant_id."""
    mod = get_tenant_mode()
    if mod == MODE_OFF:
        return document

    tenant_curent = _resolve_tenant_id(tenant_id)
    if tenant_curent is None:
        if _current_user_is_super_admin():
            return document
        if mod == MODE_OPTIONAL:
            return document
        raise TenantAccessDenied('Tenant lipsa in strict mode.')

    proiect = getattr(document, 'proiect', None)
    proiect_tenant_id = _coerce_tenant_id(getattr(proiect, 'tenant_id', None))
    if proiect is None or proiect_tenant_id != tenant_curent:
        raise TenantAccessDenied('Documentul proiect nu apartine tenantului curent.')

    return document


def require_project_document_same_tenant(document, tenant_id=None):
    """Wrapper pentru rute: ascunde DocumentProiect inaccesibil prin 404."""
    try:
        return ensure_project_document_same_tenant(document, tenant_id=tenant_id)
    except TenantAccessDenied:
        abort(404)


def query_legacy_documents_for_tenant(tenant_id=None, include_global=False):
    """Query tenant-safe pentru Document legacy prin Proiect/Angajat.

    Documentele fara proiect si fara angajat nu au ownership sigur si nu sunt
    returnate in modurile scoped. `include_global` ramane nefolosit intentionat
    pentru date operationale de tip fisier.
    """
    from models import Angajat, Document, Proiect

    query = Document.query
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

    proiect_ok = or_(
        Document.proiect_id.is_(None),
        Document.proiect.has(Proiect.tenant_id == tenant_curent),
    )
    angajat_ok = or_(
        Document.angajat_id.is_(None),
        Document.angajat.has(Angajat.tenant_id == tenant_curent),
    )
    are_owner = or_(
        Document.proiect_id.isnot(None),
        Document.angajat_id.isnot(None),
    )

    return query.filter(are_owner, proiect_ok, angajat_ok)


def get_legacy_document_or_404(document_id, tenant_id=None):
    """Returneaza Document legacy vizibil tenantului curent sau 404."""
    from models import Document

    document = query_legacy_documents_for_tenant(tenant_id=tenant_id).filter(
        Document.id == document_id
    ).first()
    if document is None:
        abort(404)
    return document


def ensure_legacy_document_same_tenant(document, tenant_id=None):
    """Valideaza Document legacy prin toti ownerii expliciti disponibili."""
    mod = get_tenant_mode()
    if mod == MODE_OFF:
        return document

    tenant_curent = _resolve_tenant_id(tenant_id)
    if tenant_curent is None:
        if _current_user_is_super_admin():
            return document
        if mod == MODE_OPTIONAL:
            return document
        raise TenantAccessDenied('Tenant lipsa in strict mode.')

    owner_tenants = []
    proiect = getattr(document, 'proiect', None)
    if getattr(document, 'proiect_id', None):
        owner_tenants.append(_coerce_tenant_id(getattr(proiect, 'tenant_id', None)))
    angajat = getattr(document, 'angajat', None)
    if getattr(document, 'angajat_id', None):
        owner_tenants.append(_coerce_tenant_id(getattr(angajat, 'tenant_id', None)))

    if not owner_tenants:
        raise TenantAccessDenied('Documentul nu are owner tenant-safe.')
    if all(owner_tenant == tenant_curent for owner_tenant in owner_tenants):
        return document

    raise TenantAccessDenied('Documentul nu apartine tenantului curent.')


def require_legacy_document_same_tenant(document, tenant_id=None):
    """Wrapper pentru rute: ascunde Document legacy inaccesibil prin 404."""
    try:
        return ensure_legacy_document_same_tenant(document, tenant_id=tenant_id)
    except TenantAccessDenied:
        abort(404)


def query_sites_for_tenant(tenant_id=None, include_global=False):
    """Query tenant-safe pentru Santier prin tenant_id direct sau Proiect."""
    from models import Santier

    query = Santier.query
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

    scope = _bim_site_scope_expr(tenant_curent, include_global=include_global)
    return query.filter(scope)


def get_site_or_404(site_id, tenant_id=None):
    """Returneaza Santier vizibil tenantului curent sau 404."""
    from models import Santier

    santier = query_sites_for_tenant(tenant_id=tenant_id).filter(
        Santier.id == site_id
    ).first()
    if santier is None:
        abort(404)
    return santier


def query_bim_buildings_for_tenant(tenant_id=None, include_global=False):
    """Query tenant-safe pentru Cladire prin Santier."""
    from models import Cladire

    query = Cladire.query
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

    return query.filter(
        Cladire.santier.has(
            _bim_site_scope_expr(tenant_curent, include_global=include_global)
        )
    )


def get_bim_building_or_404(building_id, tenant_id=None):
    """Returneaza Cladire vizibila tenantului curent sau 404."""
    from models import Cladire

    cladire = query_bim_buildings_for_tenant(tenant_id=tenant_id).filter(
        Cladire.id == building_id
    ).first()
    if cladire is None:
        abort(404)
    return cladire


def query_bim_levels_for_tenant(tenant_id=None, include_global=False):
    """Query tenant-safe pentru Nivel prin Cladire -> Santier."""
    from models import Cladire, Nivel

    query = Nivel.query
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

    return query.filter(
        Nivel.cladire.has(
            Cladire.santier.has(
                _bim_site_scope_expr(tenant_curent, include_global=include_global)
            )
        )
    )


def get_bim_level_or_404(level_id, tenant_id=None):
    """Returneaza Nivel vizibil tenantului curent sau 404."""
    from models import Nivel

    nivel = query_bim_levels_for_tenant(tenant_id=tenant_id).filter(
        Nivel.id == level_id
    ).first()
    if nivel is None:
        abort(404)
    return nivel


def query_bim_spaces_for_tenant(tenant_id=None, include_global=False):
    """Query tenant-safe pentru Spatiu prin Nivel -> Cladire -> Santier."""
    from models import Cladire, Nivel, Spatiu

    query = Spatiu.query
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

    return query.filter(
        Spatiu.nivel.has(
            Nivel.cladire.has(
                Cladire.santier.has(
                    _bim_site_scope_expr(tenant_curent, include_global=include_global)
                )
            )
        )
    )


def get_bim_space_or_404(space_id, tenant_id=None):
    """Returneaza Spatiu vizibil tenantului curent sau 404."""
    from models import Spatiu

    spatiu = query_bim_spaces_for_tenant(tenant_id=tenant_id).filter(
        Spatiu.id == space_id
    ).first()
    if spatiu is None:
        abort(404)
    return spatiu


def query_bim_models_for_tenant(tenant_id=None, include_global=False):
    """Query tenant-safe pentru ModelBIM prin tenant_id direct sau Santier."""
    from models import Cladire, ModelBIM

    query = ModelBIM.query
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

    site_scope = _bim_site_scope_expr(tenant_curent, include_global=include_global)
    parent_scope = and_(
        or_(ModelBIM.santier_id.is_(None), ModelBIM.santier.has(site_scope)),
        or_(
            ModelBIM.cladire_id.is_(None),
            ModelBIM.cladire.has(Cladire.santier.has(site_scope)),
        ),
        or_(ModelBIM.santier_id.isnot(None), ModelBIM.cladire_id.isnot(None)),
    )
    return query.filter(or_(
        ModelBIM.tenant_id == tenant_curent,
        and_(ModelBIM.tenant_id.is_(None), parent_scope),
    ))


def get_bim_model_or_404(model_id, tenant_id=None):
    """Returneaza ModelBIM vizibil tenantului curent sau 404."""
    from models import ModelBIM

    model = query_bim_models_for_tenant(tenant_id=tenant_id).filter(
        ModelBIM.id == model_id
    ).first()
    if model is None:
        abort(404)
    return model


def query_bim_model_versions_for_tenant(tenant_id=None, include_global=False):
    """Query tenant-safe pentru BIMModelVersion prin ModelBIM."""
    from models import BIMModelVersion, ModelBIM

    query = BIMModelVersion.query
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

    model_ids = query_bim_models_for_tenant(
        tenant_id=tenant_curent,
        include_global=include_global,
    ).with_entities(ModelBIM.id)
    return query.filter(or_(
        BIMModelVersion.tenant_id == tenant_curent,
        and_(
            BIMModelVersion.tenant_id.is_(None),
            BIMModelVersion.model_id.in_(model_ids),
        ),
    ))


def get_bim_model_version_or_404(version_id, tenant_id=None):
    """Returneaza BIMModelVersion vizibila tenantului curent sau 404."""
    from models import BIMModelVersion

    version = query_bim_model_versions_for_tenant(tenant_id=tenant_id).filter(
        BIMModelVersion.id == version_id
    ).first()
    if version is None:
        abort(404)
    return version


def query_bim_elements_for_tenant(tenant_id=None, include_global=False):
    """Query tenant-safe pentru ElementBIM prin ModelBIM sau ierarhia BIM."""
    from models import Cladire, ElementBIM, ModelBIM, Nivel, Spatiu

    query = ElementBIM.query
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

    site_scope = _bim_site_scope_expr(tenant_curent, include_global=include_global)
    model_ids = query_bim_models_for_tenant(
        tenant_id=tenant_curent,
        include_global=include_global,
    ).with_entities(ModelBIM.id)
    owner_scope = and_(
        or_(ElementBIM.model_bim_id.is_(None), ElementBIM.model_bim_id.in_(model_ids)),
        or_(ElementBIM.cladire_id.is_(None), ElementBIM.cladire.has(Cladire.santier.has(site_scope))),
        or_(
            ElementBIM.nivel_id.is_(None),
            ElementBIM.nivel.has(Nivel.cladire.has(Cladire.santier.has(site_scope))),
        ),
        or_(
            ElementBIM.spatiu_id.is_(None),
            ElementBIM.spatiu.has(
                Spatiu.nivel.has(Nivel.cladire.has(Cladire.santier.has(site_scope)))
            ),
        ),
        or_(
            ElementBIM.model_bim_id.isnot(None),
            ElementBIM.cladire_id.isnot(None),
            ElementBIM.nivel_id.isnot(None),
            ElementBIM.spatiu_id.isnot(None),
        ),
    )
    return query.filter(owner_scope)


def get_bim_element_or_404(element_id, tenant_id=None):
    """Returneaza ElementBIM vizibil tenantului curent sau 404."""
    from models import ElementBIM

    element = query_bim_elements_for_tenant(tenant_id=tenant_id).filter(
        ElementBIM.id == element_id
    ).first()
    if element is None:
        abort(404)
    return element


def query_bim_issues_for_tenant(tenant_id=None, include_global=False):
    """Query tenant-safe pentru IssueBIM prin tenant_id direct sau context BIM."""
    from models import Cladire, ElementBIM, IssueBIM, Nivel, Spatiu

    query = IssueBIM.query
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

    site_scope = _bim_site_scope_expr(tenant_curent, include_global=include_global)
    element_ids = query_bim_elements_for_tenant(
        tenant_id=tenant_curent,
        include_global=include_global,
    ).with_entities(ElementBIM.id)
    inherited_scope = and_(
        or_(IssueBIM.element_bim_id.is_(None), IssueBIM.element_bim_id.in_(element_ids)),
        or_(IssueBIM.cladire_id.is_(None), IssueBIM.cladire.has(Cladire.santier.has(site_scope))),
        or_(
            IssueBIM.nivel_id.is_(None),
            IssueBIM.nivel.has(Nivel.cladire.has(Cladire.santier.has(site_scope))),
        ),
        or_(
            IssueBIM.spatiu_id.is_(None),
            IssueBIM.spatiu.has(
                Spatiu.nivel.has(Nivel.cladire.has(Cladire.santier.has(site_scope)))
            ),
        ),
        or_(
            IssueBIM.element_bim_id.isnot(None),
            IssueBIM.cladire_id.isnot(None),
            IssueBIM.nivel_id.isnot(None),
            IssueBIM.spatiu_id.isnot(None),
        ),
    )
    return query.filter(or_(
        IssueBIM.tenant_id == tenant_curent,
        and_(IssueBIM.tenant_id.is_(None), inherited_scope),
    ))


def get_bim_issue_or_404(issue_id, tenant_id=None):
    """Returneaza IssueBIM vizibil tenantului curent sau 404."""
    from models import IssueBIM

    issue = query_bim_issues_for_tenant(tenant_id=tenant_id).filter(
        IssueBIM.id == issue_id
    ).first()
    if issue is None:
        abort(404)
    return issue


def ensure_bim_record_same_tenant(record, tenant_id=None):
    """Valideaza un record BIM prin tenant_id direct sau owner-ul parinte."""
    mod = get_tenant_mode()
    if mod == MODE_OFF:
        return record

    tenant_curent = _resolve_tenant_id(tenant_id)
    if tenant_curent is None:
        if _current_user_is_super_admin():
            return record
        if mod == MODE_OPTIONAL:
            return record
        raise TenantAccessDenied('Tenant lipsa in strict mode.')

    if _bim_record_belongs_to_tenant(record, tenant_curent):
        return record

    raise TenantAccessDenied('Recordul BIM nu apartine tenantului curent.')


def require_bim_record_same_tenant(record, tenant_id=None):
    """Wrapper pentru rute: ascunde recordurile BIM inaccesibile prin 404."""
    try:
        return ensure_bim_record_same_tenant(record, tenant_id=tenant_id)
    except TenantAccessDenied:
        abort(404)


def ensure_contract_inputs_same_tenant(proiect_id=None, contract_id=None, tenant_id=None):
    """Valideaza proiectul si contractul selectate in fluxurile contractuale."""
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

    from models import Contract, Proiect

    proiect_ids = _unique_positive_ints([proiect_id] if proiect_id is not None else [])
    if proiect_ids:
        proiect_ok = Proiect.query.filter(
            Proiect.id == proiect_ids[0],
            Proiect.tenant_id == tenant_curent,
        ).first()
        if proiect_ok is None:
            raise TenantAccessDenied('Proiectul nu apartine tenantului curent.')

    contract_ids = _unique_positive_ints([contract_id] if contract_id is not None else [])
    if contract_ids:
        contract_ok = Contract.query.filter(
            Contract.id == contract_ids[0],
            Contract.tenant_id == tenant_curent,
        ).first()
        if contract_ok is None:
            raise TenantAccessDenied('Contractul nu apartine tenantului curent.')

    return True


def require_contract_inputs_same_tenant(proiect_id=None, contract_id=None, tenant_id=None):
    """Wrapper pentru rute create/edit: abort daca inputurile amesteca tenanturi."""
    try:
        return ensure_contract_inputs_same_tenant(
            proiect_id=proiect_id,
            contract_id=contract_id,
            tenant_id=tenant_id,
        )
    except TenantAccessDenied:
        abort(404)


def _bim_site_scope_expr(tenant_id, include_global=False):
    from models import Proiect, Santier

    direct_scope = Santier.tenant_id == tenant_id
    proiect_scope = and_(
        Santier.tenant_id.is_(None),
        Santier.proiect.has(Proiect.tenant_id == tenant_id),
    )
    if include_global:
        return or_(
            direct_scope,
            proiect_scope,
            and_(Santier.tenant_id.is_(None), Santier.proiect_id.is_(None)),
        )
    return or_(direct_scope, proiect_scope)


def _bim_record_belongs_to_tenant(record, tenant_id):
    from models import (
        BIMCostItem, BIMModelVersion, BIMTaskSchedule, Cladire, ClashResult,
        ClashRun, ElementBIM, IssueBIM, ModelBIM, Nivel, RuleViolation,
        Santier, Spatiu, Zona,
    )

    direct_tenant = _coerce_tenant_id(getattr(record, 'tenant_id', None))
    if direct_tenant is not None:
        return direct_tenant == tenant_id

    if isinstance(record, Santier):
        return _bim_project_belongs_to_tenant(getattr(record, 'proiect', None), tenant_id)

    if isinstance(record, Cladire):
        return _bim_record_belongs_to_tenant(getattr(record, 'santier', None), tenant_id)

    if isinstance(record, Nivel):
        return _bim_record_belongs_to_tenant(getattr(record, 'cladire', None), tenant_id)

    if isinstance(record, Zona):
        return _all_present_bim_parents_match([
            (getattr(record, 'cladire_id', None), getattr(record, 'cladire', None)),
            (getattr(record, 'nivel_id', None), getattr(record, 'nivel', None)),
        ], tenant_id)

    if isinstance(record, Spatiu):
        return _all_present_bim_parents_match([
            (getattr(record, 'nivel_id', None), getattr(record, 'nivel', None)),
            (getattr(record, 'zona_id', None), getattr(record, 'zona', None)),
        ], tenant_id)

    if isinstance(record, ModelBIM):
        return _all_present_bim_parents_match([
            (getattr(record, 'santier_id', None), getattr(record, 'santier', None)),
            (getattr(record, 'cladire_id', None), getattr(record, 'cladire', None)),
        ], tenant_id)

    if isinstance(record, BIMModelVersion):
        return _bim_record_belongs_to_tenant(getattr(record, 'model', None), tenant_id)

    if isinstance(record, ElementBIM):
        model = None
        if getattr(record, 'model_bim_id', None):
            model = ModelBIM.query.get(record.model_bim_id)
        return _all_present_bim_parents_match([
            (getattr(record, 'model_bim_id', None), model),
            (getattr(record, 'cladire_id', None), getattr(record, 'cladire', None)),
            (getattr(record, 'nivel_id', None), getattr(record, 'nivel', None)),
            (getattr(record, 'spatiu_id', None), getattr(record, 'spatiu', None)),
        ], tenant_id)

    if isinstance(record, IssueBIM):
        return _all_present_bim_parents_match([
            (getattr(record, 'element_bim_id', None), getattr(record, 'element', None)),
            (getattr(record, 'cladire_id', None), getattr(record, 'cladire', None)),
            (getattr(record, 'nivel_id', None), getattr(record, 'nivel', None)),
            (getattr(record, 'spatiu_id', None), getattr(record, 'spatiu', None)),
        ], tenant_id)

    if isinstance(record, (BIMTaskSchedule, BIMCostItem)):
        return _bim_record_belongs_to_tenant(getattr(record, 'element', None), tenant_id)

    if isinstance(record, RuleViolation):
        return _all_present_bim_parents_match([
            (getattr(record, 'element_bim_id', None), getattr(record, 'element_bim', None)),
            (getattr(record, 'spatiu_id', None), getattr(record, 'spatiu', None)),
        ], tenant_id)

    if isinstance(record, ClashRun):
        return _all_present_bim_parents_match([
            (getattr(record, 'model_id', None), getattr(record, 'model', None)),
            (getattr(record, 'santier_id', None), getattr(record, 'santier', None)),
        ], tenant_id)

    if isinstance(record, ClashResult):
        return _all_present_bim_parents_match([
            (getattr(record, 'run_id', None), getattr(record, 'run', None)),
            (getattr(record, 'element_a_id', None), getattr(record, 'element_a', None)),
            (getattr(record, 'element_b_id', None), getattr(record, 'element_b', None)),
        ], tenant_id)

    return False


def _all_present_bim_parents_match(parent_pairs, tenant_id):
    has_owner = False
    for parent_id, parent in parent_pairs:
        if parent_id is None:
            continue
        has_owner = True
        if parent is None or not _bim_record_belongs_to_tenant(parent, tenant_id):
            return False
    return has_owner


def _bim_project_belongs_to_tenant(project, tenant_id):
    return (
        project is not None
        and _coerce_tenant_id(getattr(project, 'tenant_id', None)) == tenant_id
    )


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
