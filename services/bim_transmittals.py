"""
Transmittals ISO 19650 (Faza 5a BIM).

Tracking de livrare informationala: cine a primit ce versiune de model, cand.
Un transmittal leaga o BIMModelVersion de o lista de destinatari si urmareste
statusul livrarii prin tranzitii controlate:

    pregatit -> trimis -> primit
                       -> respins -> trimis (re-trimitere dupa corectii)

Oglindeste pattern-ul din services/bim_workflow.py (tranzitii cu audit).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from models import db, BIMTransmittal, BIMModelVersion
from services import audit as audit_svc


_logger = logging.getLogger(__name__)


class TransmittalError(Exception):
    """Eroare de business pe transmittals (tranzitie invalida, date lipsa)."""
    pass


def create_transmittal(version: BIMModelVersion, cod: str, *,
                       nume: Optional[str] = None,
                       destinatari: Optional[list] = None,
                       observatii: Optional[str] = None,
                       user=None, commit: bool = True) -> BIMTransmittal:
    """
    Creeaza un transmittal in stare 'pregatit' pentru o versiune de model.

    destinatari: lista de dict-uri / string-uri (nume / rol / organizatie).
    """
    if not cod or not cod.strip():
        raise TransmittalError('Codul transmittal-ului e obligatoriu.')

    tr = BIMTransmittal(
        tenant_id=getattr(user, 'tenant_id', None) if user else None,
        model_version_id=version.id,
        cod=cod.strip()[:50],
        nume=(nume or '').strip()[:200] or None,
        destinatari_json=json.dumps(destinatari, ensure_ascii=False) if destinatari else None,
        status='pregatit',
        observatii=(observatii or '').strip() or None,
        creat_de_id=getattr(user, 'id', None) if user else None,
        data_creare=datetime.utcnow(),
    )
    db.session.add(tr)
    db.session.flush()
    audit_svc.log_create('bim_transmittal', tr.id,
                         new_values={'cod': tr.cod, 'model_version_id': version.id,
                                     'status': 'pregatit'})
    if commit:
        db.session.commit()
    return tr


def schimba_status(tr: BIMTransmittal, new_status: str, user=None, *,
                   observatii: Optional[str] = None,
                   commit: bool = True) -> BIMTransmittal:
    """
    Aplica o tranzitie de status pe transmittal, cu audit.

    Ridica TransmittalError daca tranzitia nu e permisa.
    """
    valide = {s for s, _ in BIMTransmittal.STATUSURI}
    if new_status not in valide:
        raise TransmittalError(f'Status invalid: {new_status}.')
    if not tr.can_transition_to(new_status):
        raise TransmittalError(
            f'Tranzitie nepermisa: {tr.status} -> {new_status}.')

    old_status = tr.status
    tr.status = new_status
    if new_status == 'trimis':
        tr.data_trimitere = datetime.utcnow()
    if observatii:
        tr.observatii = observatii.strip() or None

    audit_svc.log(
        action=f'transmittal_{new_status}',
        entity_type='bim_transmittal',
        entity_id=tr.id,
        old_values={'status': old_status},
        new_values={'status': new_status},
    )

    if commit:
        db.session.commit()
    return tr
