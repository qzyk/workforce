"""Project service — boundary tenant-safe pentru domeniul Proiect (read-only).

S1.3A extrage din routes/proiecte.py logica de asamblare a contextului de
listare si datele financiare read-only. Serviciul este HTTP-free: nu apeleaza
API-ul de raspuns Flask (ruta pastreaza request args, render, flash, redirect).
In S1.3A serviciul este strict read-only — nu adauga, nu sterge, fara commit.
Proiect este tenant-scoped direct prin Proiect.tenant_id; toate citirile trec
prin helperii din services/security/tenant_access.py. Logica de create/edit/
status si rutele cross-domeniu raman in ruta (S1.3B / gate-uri ulterioare).
"""

from datetime import date, timedelta

from models import db, Proiect, Angajat, AngajatProiect, Pontaj, Utilizator
from services.security.tenant_access import (
    query_for_tenant,
    query_project_assignments_for_tenant,
    query_timesheets_for_tenant,
    query_users_for_tenant,
)


# ============================================================
# Lista proiecte (read-only, tenant-safe)
# ============================================================

def get_project_managers(*, tenant_id=None):
    """Managerii/adminii activi vizibili tenantului curent (pentru filtre/form).

    Identic cu interogarea folosita in ruta lista si _populeaza_manageri_form.
    """
    return query_users_for_tenant(tenant_id=tenant_id).filter(
        Utilizator.rol.in_(['admin', 'manager']),
        Utilizator.activ == True
    ).order_by(Utilizator.nume, Utilizator.prenume).all()


def get_project_list_context(*, page=1, status_filtru='', cautare='',
                             manager_filtru='', sort='data_start_desc',
                             view_mode='cards', tenant_id=None):
    """Asambleaza contextul tenant-safe pentru panoul de listare proiecte (ruta lista).

    Ruta ramane responsabila pentru argumentele din query string si pentru
    randare. Serviciul construieste query-ul filtrat/sortat/paginat, statisticile si lista de
    manageri, identic cu ruta veche. Returneaza un dict gata de pasat ca
    **kwargs catre proiecte/lista.html. Nu muteaza nimic.
    """
    query = query_for_tenant(Proiect, tenant_id=tenant_id)

    if status_filtru:
        query = query.filter_by(status=status_filtru)
    if cautare:
        query = query.filter(
            db.or_(
                Proiect.nume.ilike(f'%{cautare}%'),
                Proiect.cod_proiect.ilike(f'%{cautare}%'),
                Proiect.beneficiar.ilike(f'%{cautare}%')
            )
        )
    if manager_filtru:
        query = query.filter_by(manager_id=int(manager_filtru))

    # Sortare (modurile exacte din ruta)
    if sort == 'nume_asc':
        query = query.order_by(Proiect.nume.asc())
    elif sort == 'nume_desc':
        query = query.order_by(Proiect.nume.desc())
    elif sort == 'data_start_asc':
        query = query.order_by(Proiect.data_start.asc())
    elif sort == 'buget_desc':
        query = query.order_by(Proiect.buget_total.desc().nullslast())
    elif sort == 'status':
        query = query.order_by(Proiect.status.asc())
    else:
        query = query.order_by(Proiect.data_start.desc())

    pagination = query.paginate(page=page, per_page=12, error_out=False)
    proiecte = pagination.items

    # Statistici (acelasi query tenant-safe)
    stats_query = query_for_tenant(Proiect, tenant_id=tenant_id)
    total_active = stats_query.filter_by(status='activ').count()
    total_planificate = stats_query.filter_by(status='planificat').count()
    total_finalizate = stats_query.filter_by(status='finalizat').count()
    total_suspendate = stats_query.filter_by(status='suspendat').count()
    buget_total_all = stats_query.with_entities(db.func.sum(Proiect.buget_total)).filter(
        Proiect.status.in_(['activ', 'planificat'])
    ).scalar() or 0

    manageri = get_project_managers(tenant_id=tenant_id)

    return {
        'proiecte': proiecte,
        'pagination': pagination,
        'status_filtru': status_filtru,
        'cautare': cautare,
        'manager_filtru': manager_filtru,
        'sort': sort,
        'view_mode': view_mode,
        'total_active': total_active,
        'total_planificate': total_planificate,
        'total_finalizate': total_finalizate,
        'total_suspendate': total_suspendate,
        'buget_total_all': buget_total_all,
        'manageri': manageri,
    }


# ============================================================
# Date financiare proiect (read-only, tenant-safe)
# ============================================================

def get_project_total_hours(proiect_id, *, tenant_id=None):
    """Total ore lucrate pentru proiect, calculat prin Pontaj tenant-safe."""
    result = query_timesheets_for_tenant(tenant_id=tenant_id).filter(
        Pontaj.proiect_id == proiect_id
    ).with_entities(db.func.sum(Pontaj.ore_lucrate)).scalar()
    return float(result) if result else 0


def calculate_project_labor_cost(proiect_id, *, tenant_id=None):
    """Calculeaza costul total al manoperei pe proiect."""
    pontaje_ids = query_timesheets_for_tenant(tenant_id=tenant_id).filter(
        Pontaj.proiect_id == proiect_id
    ).with_entities(Pontaj.id)
    asignari_ids = query_project_assignments_for_tenant(
        project_id=proiect_id, tenant_id=tenant_id
    ).with_entities(AngajatProiect.id)
    result = db.session.query(
        db.func.sum(
            Pontaj.ore_normale * db.func.coalesce(AngajatProiect.tarif_negociat, 0) +
            Pontaj.ore_suplimentare_50 * db.func.coalesce(AngajatProiect.tarif_negociat, 0) * 1.5 +
            Pontaj.ore_suplimentare_100 * db.func.coalesce(AngajatProiect.tarif_negociat, 0) * 2
        )
    ).join(AngajatProiect, db.and_(
        AngajatProiect.angajat_id == Pontaj.angajat_id,
        AngajatProiect.proiect_id == Pontaj.proiect_id
    )).filter(
        Pontaj.id.in_(pontaje_ids),
        AngajatProiect.id.in_(asignari_ids),
    ).scalar()
    return float(result) if result else 0


def get_project_weekly_hours(proiect_id, *, weeks=12, tenant_id=None):
    """Returneaza orele lucrate pe saptamana pentru ultimele N saptamani."""
    results = []
    today = date.today()
    for i in range(weeks - 1, -1, -1):
        start = today - timedelta(days=today.weekday() + 7 * i)
        end = start + timedelta(days=6)
        ore = query_timesheets_for_tenant(tenant_id=tenant_id).filter(
            Pontaj.proiect_id == proiect_id,
            Pontaj.data >= start,
            Pontaj.data <= end
        ).with_entities(db.func.sum(Pontaj.ore_lucrate)).scalar()
        results.append({
            'label': f'S{start.isocalendar()[1]}',
            'start': start.strftime('%d.%m'),
            'end': end.strftime('%d.%m'),
            'ore': float(ore) if ore else 0
        })
    return results


def get_project_monthly_costs(proiect_id, *, months=6, tenant_id=None):
    """Returneaza costul manoperei pe luna pentru ultimele N luni."""
    results = []
    today = date.today()
    for i in range(months - 1, -1, -1):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1

        pontaje_ids = query_timesheets_for_tenant(tenant_id=tenant_id).filter(
            Pontaj.proiect_id == proiect_id,
            db.extract('month', Pontaj.data) == m,
            db.extract('year', Pontaj.data) == y
        ).with_entities(Pontaj.id)
        asignari_ids = query_project_assignments_for_tenant(
            project_id=proiect_id, tenant_id=tenant_id
        ).with_entities(AngajatProiect.id)
        cost = db.session.query(
            db.func.sum(
                Pontaj.ore_lucrate * db.func.coalesce(AngajatProiect.tarif_negociat, 0)
            )
        ).join(AngajatProiect, db.and_(
            AngajatProiect.angajat_id == Pontaj.angajat_id,
            AngajatProiect.proiect_id == Pontaj.proiect_id
        )).filter(
            Pontaj.id.in_(pontaje_ids),
            AngajatProiect.id.in_(asignari_ids),
        ).scalar()

        month_names = ['', 'Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun',
                       'Iul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        results.append({
            'label': f'{month_names[m]} {y}',
            'cost': float(cost) if cost else 0
        })
    return results
