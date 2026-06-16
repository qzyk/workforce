"""
Serviciu CDE workflow pentru BIMModelVersion (Faza 3).

ISO 19650 simplificat:
    wip       -> shared / archived
    shared    -> published / rejected / wip / archived
    published -> archived
    rejected  -> wip / archived
    archived  -> (terminal)

Reguli de permisiuni:
- Orice user autentificat poate face: upload versiune (-> wip), share (wip -> shared)
- Doar admin/manager poate: publish (shared -> published), reject (shared -> rejected),
  archive, restart (rejected -> wip)
- Versiunea propriei discipline poate fi adusa inapoi din shared in wip de catre creator;
  dupa publish, doar admin/manager poate arhiva.

Toate tranzitiile se logheaza in audit_log (entity_type='bim_model_version').
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from models import db, BIMModelVersion
from services import audit as audit_svc


class WorkflowError(Exception):
    """Tranzitie de status nepermisa sau eroare in workflow."""


# Tranzitii care necesita rol elevat (admin sau manager)
TRANZITII_PRIVILEGIATE = {
    ('shared', 'published'),
    ('shared', 'rejected'),
    ('published', 'archived'),
    ('rejected', 'wip'),
    ('rejected', 'archived'),
    ('shared', 'archived'),
    ('wip', 'archived'),
}


# Maparea tranzitiilor privilegiate la actiuni RBAC (services/rbac.py).
# Folosita doar cand flag-ul 'bim-rbac-fine' e ON. share-ul (wip->shared)
# nu e privilegiat, dar il mapam pentru completitudine cand verificam fin.
TRANZITIE_LA_ACTIUNE_RBAC = {
    ('wip', 'shared'): 'version:share',
    ('shared', 'published'): 'version:publish',
    ('shared', 'rejected'): 'version:reject',
    ('published', 'archived'): 'version:archive',
    ('shared', 'archived'): 'version:archive',
    ('wip', 'archived'): 'version:archive',
    ('rejected', 'archived'): 'version:archive',
    ('rejected', 'wip'): 'version:publish',  # restart workflow: tratat ca privilegiu de publish
}


def _user_is_manager_or_admin(user) -> bool:
    return bool(user) and getattr(user, 'rol', None) in ('admin', 'manager')


def _rbac_fine_enabled() -> bool:
    """True cand flag-ul 'bim-rbac-fine' e activ (per tenant sau global)."""
    try:
        from services import feature_flags as ff
        return ff.is_enabled('bim-rbac-fine')
    except Exception:
        return False


def _scope_din_versiune(version: BIMModelVersion) -> dict:
    """
    Extrage scope-ul (santier_id / cladire_id / disciplina) din versiune,
    pentru a-l da lui rbac.has_permission. Disciplina e pe versiune; santier
    si cladire vin de pe modelul parinte (best-effort, degradare gratioasa)."""
    santier_id = None
    cladire_id = None
    try:
        model = version.model
        if model is not None:
            santier_id = getattr(model, 'santier_id', None)
            cladire_id = getattr(model, 'cladire_id', None)
    except Exception:
        pass
    return {
        'santier_id': santier_id,
        'cladire_id': cladire_id,
        'disciplina': version.disciplina,
    }


def _permite_rbac_fin(user, version: BIMModelVersion, action: str) -> bool:
    """
    Verifica permisiunea fina prin rbac.has_permission pe scope-ul versiunii.
    Import lazy ca sa nu cuplam workflow-ul de rbac la incarcare."""
    try:
        from services import rbac
    except Exception:
        return False
    scope = _scope_din_versiune(version)
    return rbac.has_permission(user, action, **scope)


def _user_is_creator(user, version: BIMModelVersion) -> bool:
    return bool(user) and version.creat_de_id == getattr(user, 'id', None)


def can_user_transition(user, version: BIMModelVersion, new_status: str) -> tuple[bool, str]:
    """
    Verifica daca user-ul poate face tranzitia. Returneaza (allowed, motiv).
    Motivul e mesaj care poate fi afisat user-ului in flash().
    """
    if version.is_terminal:
        return False, 'Versiunea e arhivata; nu mai accepta tranzitii.'

    if not version.can_transition_to(new_status):
        return False, (
            f'Tranzitie nepermisa: {version.status} -> {new_status}. '
            f'Stari valide din "{version.status}": '
            f'{sorted(version.TRANZITII_VALIDE.get(version.status, set()))}'
        )

    transition_key = (version.status, new_status)

    rbac_fin = _rbac_fine_enabled()

    # Tranzitiile privilegiate cer autorizare.
    # - flag 'bim-rbac-fine' OFF (default): rol elevat admin/manager (comportament istoric).
    # - flag ON: permisiune RBAC fina pe scope-ul disciplinei/santierului versiunii,
    #   SAU rol elevat admin/manager (admin-ul tenant bypaseaza oricum in has_permission).
    if transition_key in TRANZITII_PRIVILEGIATE:
        if rbac_fin:
            action = TRANZITIE_LA_ACTIUNE_RBAC.get(transition_key)
            if action and _permite_rbac_fin(user, version, action):
                pass  # autorizat fin
            elif _user_is_manager_or_admin(user):
                pass  # fallback pe rolul global (admin/manager raman privilegiati)
            else:
                disc = version.disciplina or 'aceasta disciplina'
                return False, (
                    f'Nu ai permisiunea RBAC pentru aceasta tranzitie pe disciplina {disc}. '
                    f'Necesita un rol BIM cu "{action}" pe scope-ul versiunii.'
                )
        else:
            if not _user_is_manager_or_admin(user):
                return False, 'Doar managerii / administratorii pot face aceasta tranzitie.'

    # Caz special: shared -> wip (rollback to draft).
    # Permis creatorului versiunii sau admin/manager. Cu flag fin ON, si
    # detinatorilor de permisiune 'version:share' pe disciplina (echipa task team).
    if transition_key == ('shared', 'wip'):
        autorizat = _user_is_creator(user, version) or _user_is_manager_or_admin(user)
        if not autorizat and rbac_fin:
            autorizat = _permite_rbac_fin(user, version, 'version:share')
        if not autorizat:
            return False, 'Doar autorul sau un manager poate retrage o versiune din shared.'

    return True, 'OK'


def transition(
    version: BIMModelVersion,
    new_status: str,
    user,
    *,
    comentariu: Optional[str] = None,
    commit: bool = True,
) -> BIMModelVersion:
    """
    Aplica tranzitia status -> new_status pe versiune.
    Loaheaza in audit_log + actualizeaza timestamps + (opt) salveaza.

    Ridica WorkflowError daca tranzitia nu e permisa.
    """
    allowed, motiv = can_user_transition(user, version, new_status)
    if not allowed:
        raise WorkflowError(motiv)

    old_status = version.status
    version.status = new_status

    # Update timestamps + cine a aprobat
    now = datetime.utcnow()
    if new_status == 'shared':
        version.data_share = now
    elif new_status == 'published':
        version.data_publicare = now
        version.aprobat_de_id = getattr(user, 'id', None)
    elif new_status == 'rejected':
        version.data_respingere = now
        version.aprobat_de_id = getattr(user, 'id', None)
        if comentariu:
            version.comentariu_aprobare = comentariu
    elif new_status == 'archived':
        version.data_arhivare = now

    # Audit log
    audit_svc.log(
        action=f'workflow_{new_status}',
        entity_type='bim_model_version',
        entity_id=version.id,
        old_values={'status': old_status},
        new_values={'status': new_status, 'comentariu': comentariu} if comentariu
                   else {'status': new_status},
    )

    if commit:
        db.session.commit()
    return version


def create_new_version(
    model,
    versiune: str,
    user,
    *,
    disciplina: Optional[str] = None,
    descriere: Optional[str] = None,
    fisier_path: Optional[str] = None,
    fisier_marime: Optional[int] = None,
    extern_url: Optional[str] = None,
    tenant_id: Optional[int] = None,
    commit: bool = True,
) -> BIMModelVersion:
    """
    Helper pentru a crea o versiune noua (status='wip' implicit).
    Loaheaza creatia in audit.
    """
    if not versiune or not versiune.strip():
        raise WorkflowError('Eticheta versiunii e obligatorie.')

    # Verific unicitate (model_id + versiune)
    existing = BIMModelVersion.query.filter_by(model_id=model.id,
                                               versiune=versiune.strip()).first()
    if existing:
        raise WorkflowError(
            f'Exista deja versiunea "{versiune}" pentru acest model.'
        )

    v = BIMModelVersion(
        tenant_id=tenant_id,
        model_id=model.id,
        versiune=versiune.strip(),
        disciplina=(disciplina or '').strip().upper() or None,
        descriere=(descriere or '').strip() or None,
        status='wip',
        fisier_path=fisier_path,
        fisier_marime=fisier_marime,
        extern_url=extern_url,
        creat_de_id=getattr(user, 'id', None),
    )
    db.session.add(v)
    db.session.flush()  # pentru a avea v.id

    audit_svc.log_create(
        'bim_model_version', v.id,
        new_values={
            'model_id': model.id,
            'versiune': v.versiune,
            'disciplina': v.disciplina,
            'status': v.status,
        },
    )

    if commit:
        db.session.commit()
    return v


def get_published_versions_for_santier(santier_id: int) -> list[BIMModelVersion]:
    """
    Toate versiunile 'published' pentru toate modelele unui santier.
    Folosit la federation viewer.

    Tenant scoping: in mod 'off' query-ul ramane identic; in 'strict'
    filtreaza pe tenant_id-ul versiunii (BIMModelVersion are tenant_id nullable).
    """
    from models import ModelBIM
    from tenant import with_tenant_scope
    q = (BIMModelVersion.query
         .join(ModelBIM, ModelBIM.id == BIMModelVersion.model_id)
         .filter(ModelBIM.santier_id == santier_id,
                 BIMModelVersion.status == 'published'))
    q = with_tenant_scope(q, BIMModelVersion)
    return (q.order_by(BIMModelVersion.disciplina,
                       BIMModelVersion.data_publicare.desc())
            .all())


def get_latest_version(model_id: int, status: Optional[str] = None) -> Optional[BIMModelVersion]:
    """Cea mai recenta versiune pentru un model (eventual filtrata pe status)."""
    q = BIMModelVersion.query.filter_by(model_id=model_id)
    if status:
        q = q.filter_by(status=status)
    return q.order_by(BIMModelVersion.data_creare.desc()).first()
