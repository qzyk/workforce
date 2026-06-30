"""Project service — boundary tenant-safe pentru domeniul Proiect.

S1.3A extrage din routes/proiecte.py logica de asamblare a contextului de
listare si datele financiare read-only. S1.3B adauga salvarile mutante
create/edit/status (adauga, editeaza, schimba_status). Serviciul este HTTP-free:
nu apeleaza API-ul de raspuns Flask (ruta pastreaza request args, ProiectForm,
validate_on_submit, auto-cod GET prefill, render, flash, redirect, jsonify).
Proiect este tenant-scoped direct prin Proiect.tenant_id; toate citirile trec
prin helperii din services/security/tenant_access.py. Pentru salvari serviciul
face commit; ruta face rollback pe exceptii (conventia S1.x). Rutele cross-domeniu
(detalii, hub, resurse nested, rapoarte/export) raman in ruta.
"""

from datetime import date, timedelta

from models import db, Proiect, Angajat, AngajatProiect, Pontaj, Utilizator
from services.security.tenant_access import (
    query_for_tenant,
    query_project_assignments_for_tenant,
    query_timesheets_for_tenant,
    query_users_for_tenant,
    tenant_id_for_new_record_or_403,
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


# ============================================================
# Salvari create/edit/status (mutante, tenant-safe)
# ============================================================

def _compose_project_location(judet, localitate):
    """Compune locatia din judet + localitate, identic cu adauga/editeaza.

    locatie = judet; daca exista si localitate si judet -> "localitate, judet".
    """
    judet = judet or ''
    localitate = localitate or ''
    locatie = judet
    if localitate and judet:
        locatie = f'{localitate}, {judet}'
    return locatie


def _validate_project_manager(manager_id, *, tenant_id=None):
    """Valideaza managerul selectat prin query_users_for_tenant.

    Identic cu ruta: daca s-a ales un manager, acesta trebuie sa fie vizibil
    tenantului curent, altfel first_or_404 ridica 404 (fara incredere oarba in
    manager_id-ul din formular).
    """
    if manager_id:
        query_users_for_tenant(tenant_id=tenant_id).filter(
            Utilizator.id == manager_id
        ).first_or_404()


def create_project_from_form_data(*, form_data, tenant_id=None):
    """Creeaza un Proiect din ProiectForm validat (ruta adauga POST).

    Ruta pastreaza ProiectForm, _populeaza_manageri_form, validate_on_submit,
    auto-cod GET prefill, flash si redirect. Serviciul pastreaza asignarea
    tenant_id, validarea managerului, compunerea locatiei, maparea campurilor cu
    default-urile existente si commit-ul. Returneaza Proiectul creat.

    Daca tenant_id este None, se rezolva prin tenant_id_for_new_record_or_403()
    (fail-closed in strict fara tenant), exact ca in ruta.
    """
    tenant_id_nou = tenant_id if tenant_id is not None else tenant_id_for_new_record_or_403()
    manager_id = form_data.manager_id.data
    _validate_project_manager(manager_id, tenant_id=tenant_id_nou)
    locatie = _compose_project_location(form_data.judet.data, form_data.localitate.data)

    proiect = Proiect(
        cod_proiect=form_data.cod_proiect.data.strip(),
        nume=form_data.nume.data.strip(),
        descriere=form_data.descriere.data or '',
        locatie=locatie,
        adresa_santier=form_data.adresa_santier.data or '',
        beneficiar=form_data.beneficiar.data or '',
        nr_contract_beneficiar=form_data.nr_contract_beneficiar.data or '',
        data_start=form_data.data_start.data,
        data_sfarsit_planificat=form_data.data_sfarsit_planificat.data,
        status=form_data.status.data,
        manager_id=manager_id if manager_id else None,
        buget_total=form_data.buget_total.data,
        buget_manopera=form_data.buget_manopera.data,
        tenant_id=tenant_id_nou,
    )
    db.session.add(proiect)
    db.session.commit()
    return proiect


def update_project_from_form_data(*, project, form_data, tenant_id=None):
    """Actualizeaza un Proiect existent din ProiectForm validat (ruta editeaza POST).

    Ruta pastreaza get_project_or_404, ProiectForm(obj=...), validate_on_submit,
    GET locatie split, flash si redirect. Serviciul pastreaza validarea
    managerului, compunerea locatiei, maparea campurilor (inclusiv
    data_sfarsit_real) si commit-ul. Nu incarca obiectul dupa ID — ruta il
    transmite deja validat tenant-safe. Returneaza Proiectul actualizat.
    """
    manager_id = form_data.manager_id.data
    _validate_project_manager(manager_id, tenant_id=tenant_id)
    locatie = _compose_project_location(form_data.judet.data, form_data.localitate.data)

    project.cod_proiect = form_data.cod_proiect.data.strip()
    project.nume = form_data.nume.data.strip()
    project.descriere = form_data.descriere.data or ''
    project.locatie = locatie
    project.adresa_santier = form_data.adresa_santier.data or ''
    project.beneficiar = form_data.beneficiar.data or ''
    project.nr_contract_beneficiar = form_data.nr_contract_beneficiar.data or ''
    project.data_start = form_data.data_start.data
    project.data_sfarsit_planificat = form_data.data_sfarsit_planificat.data
    project.data_sfarsit_real = form_data.data_sfarsit_real.data
    project.status = form_data.status.data
    project.manager_id = manager_id if manager_id else None
    project.buget_total = form_data.buget_total.data
    project.buget_manopera = form_data.buget_manopera.data

    db.session.commit()
    return project


def change_project_status(*, project, new_status):
    """Schimba statusul unui Proiect deja incarcat (ruta schimba_status).

    Validarea statusului se face fata de Proiect.STATUSURI. La status invalid
    returneaza un rezultat simplu pe care ruta il mapeaza la JSON 400, FARA sa
    muteze sau sa comita. La status valid seteaza statusul, seteaza
    data_sfarsit_real doar daca lipseste cand statusul devine 'finalizat', si
    face commit. Returneaza un dict (nu un Response Flask).
    """
    valid_statuses = [s[0] for s in Proiect.STATUSURI]
    if new_status not in valid_statuses:
        return {'success': False, 'error': 'Status invalid', 'status_code': 400}

    project.status = new_status
    if new_status == 'finalizat' and not project.data_sfarsit_real:
        project.data_sfarsit_real = date.today()

    db.session.commit()
    return {'success': True, 'status': new_status}
