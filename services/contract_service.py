"""Service boundary pentru Contract core list (C1A).

C1A extrage doar asamblarea contextului de listare contracte. Serviciul ramane
read-only, fara raspunsuri Flask si fara tranzactii. Rutele pastreaza
decoratorii, parsarea query-string-ului si randarea.
"""

from models import Contract, Proiect, db
from services.security.tenant_access import query_contracts_for_tenant, query_for_tenant


def _numar_acte_aditionale_vizibile(contract_ids, *, tenant_id=None):
    """Numar acte aditionale tenant-safe pentru contractele afisate."""
    if not contract_ids:
        return {}

    rows = query_contracts_for_tenant(tenant_id=tenant_id).with_entities(
        Contract.parinte_contract_id,
        db.func.count(Contract.id),
    ).filter(
        Contract.parinte_contract_id.in_(contract_ids)
    ).group_by(Contract.parinte_contract_id).all()
    return {contract_id: count for contract_id, count in rows}


def get_contract_list_context(*, status_filter=None, project_id=None, search='',
                              tenant_id=None):
    """Asambleaza contextul tenant-safe pentru lista contractelor.

    Returneaza exact cheile consumate de template-ul `contracte/lista.html`.
    Validarea proiectului filtrat ramane in ruta, care apeleaza
    `get_project_or_404` inainte de delegare.
    """
    status_filtru = (status_filter or '').strip()
    proiect_filtru = project_id
    cautare = (search or '').strip()

    query = query_contracts_for_tenant(tenant_id=tenant_id)
    if status_filtru:
        query = query.filter_by(status=status_filtru)
    if proiect_filtru:
        query = query.filter_by(proiect_id=proiect_filtru)
    if cautare:
        query = query.filter(
            db.or_(
                Contract.nr_contract.ilike(f'%{cautare}%'),
                Contract.beneficiar.ilike(f'%{cautare}%'),
                Contract.antreprenor.ilike(f'%{cautare}%'),
            )
        )

    query = query.filter(Contract.parinte_contract_id.is_(None))
    contracte = query.order_by(Contract.data_semnare.desc()).all()
    acte_aditionale_count_by_contract_id = _numar_acte_aditionale_vizibile(
        [c.id for c in contracte],
        tenant_id=tenant_id,
    )

    total_activ = query_contracts_for_tenant(tenant_id=tenant_id).filter_by(
        status='activ', parinte_contract_id=None
    ).count()
    total_finalizat = query_contracts_for_tenant(tenant_id=tenant_id).filter_by(
        status='finalizat', parinte_contract_id=None
    ).count()
    total_suspendat = query_contracts_for_tenant(tenant_id=tenant_id).filter_by(
        status='suspendat', parinte_contract_id=None
    ).count()

    proiecte = query_for_tenant(Proiect, tenant_id=tenant_id).order_by(
        Proiect.cod_proiect
    ).all()

    return {
        'contracte': contracte,
        'proiecte': proiecte,
        'status_filtru': status_filtru,
        'proiect_filtru': proiect_filtru,
        'cautare': cautare,
        'total_activ': total_activ,
        'total_finalizat': total_finalizat,
        'total_suspendat': total_suspendat,
        'acte_aditionale_count_by_contract_id': acte_aditionale_count_by_contract_id,
        'statuses': Contract.STATUSES,
    }
