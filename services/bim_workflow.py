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


def _user_is_manager_or_admin(user) -> bool:
    return bool(user) and getattr(user, 'rol', None) in ('admin', 'manager')


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

    # Tranzitiile privilegiate cer rol elevat
    if transition_key in TRANZITII_PRIVILEGIATE:
        if not _user_is_manager_or_admin(user):
            return False, 'Doar managerii / administratorii pot face aceasta tranzitie.'

    # Caz special: shared -> wip (rollback to draft).
    # Permis creatorului versiunii sau admin/manager.
    if transition_key == ('shared', 'wip'):
        if not (_user_is_creator(user, version) or _user_is_manager_or_admin(user)):
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
