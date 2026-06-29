"""
EDIFICO WORKFORCE - Service layer pentru pontaje / timesheet (S1.2A).

Primul boundary de serviciu pentru domeniul Pontaj. Conform deciziei D015,
logica de timesheet traieste intr-un fisier NOU, separat de activity_service.

S1.2A extrage DOAR:
  * calculul pur de ore (calculate_timesheet_hours);
  * contextul de citire/listare tenant-safe pentru rutele GET/AJAX low-risk
    (lista, situatie zilnica, calendar angajat, aprobare GET, angajati pe
    proiect, verificare duplicat).

NU contine si nu trebuie sa contina in S1.2A (raman in rute, extrase ulterior
in S1.2B/C/D):
  * salvarea create/edit (adauga, adauga_multiplu, editeaza POST);
  * tranzitiile de workflow (aproba/respinge/trimite/aproba_multiplu);
  * export/import (export_lunar, import_excel, template_import).

Toate query-urile pe date operationale tenant-owned folosesc helperii din
services/security/tenant_access.py. SarbatoareLegala este catalog global
(non-tenant) si ramane query direct, identic cu rutele de dinainte.

Serviciul este HTTP-free: fara flash/redirect/render_template/jsonify/request/
send_file. S1.2A este READ-ONLY: nu muteaza nimic si nu face commit/rollback.
"""

import calendar
from datetime import datetime, date

from models import db, Pontaj, Angajat, Proiect, AngajatProiect, SarbatoareLegala
from services.security.tenant_access import (
    get_project_or_404,
    query_for_tenant,
    query_timesheets_for_tenant,
)


# ============================================================
# Calcul pur de ore (fara stare, fara HTTP)
# ============================================================

def calculate_timesheet_hours(*, ora_start, ora_sfarsit, tip_zi, data_pontaj=None):
    """Calculeaza orele lucrate conform legislatiei constructiilor.

    Mutat din routes/pontaje.py::calculate_hours, comportament identic.
    Returneaza dict cu ore_lucrate, ore_normale, ore_supl_50, ore_supl_100, tip_zi.
    SarbatoareLegala este catalog global (non-tenant).
    """
    try:
        h1, m1 = map(int, ora_start.split(':'))
        h2, m2 = map(int, ora_sfarsit.split(':'))
    except (ValueError, AttributeError):
        return {'ore_lucrate': 0, 'ore_normale': 0, 'ore_supl_50': 0, 'ore_supl_100': 0}

    total_min = (h2 * 60 + m2) - (h1 * 60 + m1)
    if total_min <= 0:
        total_min += 24 * 60  # tura de noapte

    # Limita 12h/zi
    if total_min > 12 * 60:
        total_min = 12 * 60

    # Pauza masa 30 min dedusa daca > 6h
    if total_min > 6 * 60:
        total_min -= 30

    ore_lucrate = round(total_min / 60, 2)

    # Detectie sarbatoare legala
    is_sarbatoare = False
    if data_pontaj:
        is_sarbatoare = SarbatoareLegala.query.filter_by(data=data_pontaj).first() is not None

    # Detectie tip zi automat din data
    if data_pontaj and tip_zi == 'lucratoare':
        dow = data_pontaj.weekday()  # 0=Lu, 5=Sa, 6=Du
        if is_sarbatoare:
            tip_zi = 'sarbatoare_legala'
        elif dow == 5:
            tip_zi = 'sambata'
        elif dow == 6:
            tip_zi = 'duminica'

    # Calcul ore
    ore_normale = 0
    ore_supl_50 = 0
    ore_supl_100 = 0

    if tip_zi in ('duminica', 'sarbatoare_legala'):
        # Toate orele sunt 100%
        ore_supl_100 = ore_lucrate
    elif tip_zi == 'sambata':
        # Toate orele sambata sunt 50%
        ore_supl_50 = ore_lucrate
    elif tip_zi in ('co', 'cm', 'invoiere'):
        # Tipuri speciale - nu se calculeaza ore suplimentare
        ore_normale = ore_lucrate
    else:
        # Zi lucratoare normala
        ore_normale = min(8, ore_lucrate)
        extra = max(0, ore_lucrate - 8)
        if extra > 0:
            # Ore 8-10 = 50%, ore > 10 = 100%
            ore_supl_50 = min(2, extra)
            ore_supl_100 = max(0, extra - 2)

    return {
        'ore_lucrate': ore_lucrate,
        'ore_normale': round(ore_normale, 2),
        'ore_supl_50': round(ore_supl_50, 2),
        'ore_supl_100': round(ore_supl_100, 2),
        'tip_zi': tip_zi
    }


# ============================================================
# Context de citire/listare tenant-safe (read-only)
# ============================================================

def get_timesheet_list_context(*, filters, tenant_id=None):
    """Construieste contextul tenant-safe pentru panoul de pontaje (ruta lista).

    `filters` este un dict cu cheile din query string: luna, anul, data,
    proiect_id, angajat_id, status. Returneaza un dict gata de pasat ca **kwargs
    catre templateul pontaje/panou.html. Nu muteaza nimic.
    """
    today = date.today()
    luna = filters.get('luna') or today.month
    anul = filters.get('anul') or today.year

    # Statistici azi
    total_angajati_activi = query_for_tenant(Angajat, tenant_id=tenant_id).filter_by(
        status='activ'
    ).count()
    pontaje_azi = query_timesheets_for_tenant(tenant_id=tenant_id).filter_by(data=today).count()
    pontaje_de_aprobat = query_timesheets_for_tenant(tenant_id=tenant_id).filter_by(
        status='trimis'
    ).count()

    # Calendar lunar - date per zi
    _, days_in_month = calendar.monthrange(anul, luna)
    calendar_data = []
    for day in range(1, days_in_month + 1):
        d = date(anul, luna, day)
        nr_pontaje = query_timesheets_for_tenant(tenant_id=tenant_id).filter_by(data=d).count()
        is_sarb = SarbatoareLegala.query.filter_by(data=d).first()
        dow = d.weekday()

        if dow >= 5 or is_sarb:
            tip = 'weekend' if dow >= 5 else 'sarbatoare'
        elif d > today:
            tip = 'viitor'
        elif nr_pontaje == 0:
            tip = 'zero'
        else:
            pct = (nr_pontaje / total_angajati_activi * 100) if total_angajati_activi > 0 else 0
            if pct >= 80:
                tip = 'plin'
            elif pct >= 50:
                tip = 'bun'
            elif pct >= 20:
                tip = 'mediu'
            else:
                tip = 'slab'

        calendar_data.append({
            'zi': day,
            'data': d,
            'dow': dow,
            'nr_pontaje': nr_pontaje,
            'tip': tip,
            'is_today': d == today
        })

    # Pontaje recente (cu filtre)
    data_filtru = filters.get('data', '')
    proiect_id = filters.get('proiect_id', '')
    angajat_id = filters.get('angajat_id', '')
    status_filtru = filters.get('status', '')

    query = query_timesheets_for_tenant(tenant_id=tenant_id)
    if data_filtru:
        query = query.filter(Pontaj.data == datetime.strptime(data_filtru, '%Y-%m-%d').date())
    if proiect_id:
        query = query.filter(Pontaj.proiect_id == int(proiect_id))
    if angajat_id:
        query = query.filter(Pontaj.angajat_id == int(angajat_id))
    if status_filtru:
        query = query.filter(Pontaj.status == status_filtru)

    pontaje = query.order_by(Pontaj.data.desc(), Pontaj.id.desc()).limit(100).all()

    proiecte = query_for_tenant(Proiect, tenant_id=tenant_id).filter(
        Proiect.status.in_(['activ', 'planificat'])
    ).order_by(Proiect.cod_proiect).all()
    angajati = query_for_tenant(Angajat, tenant_id=tenant_id).filter_by(
        status='activ'
    ).order_by(Angajat.nume).all()

    # First day padding
    first_dow = date(anul, luna, 1).weekday()  # 0=Luni

    return {
        'pontaje': pontaje,
        'proiecte': proiecte,
        'angajati': angajati,
        'calendar_data': calendar_data,
        'first_dow': first_dow,
        'luna': luna,
        'anul': anul,
        'today': today,
        'total_angajati_activi': total_angajati_activi,
        'pontaje_azi': pontaje_azi,
        'pontaje_de_aprobat': pontaje_de_aprobat,
        'data_filtru': data_filtru,
        'proiect_id_filtru': proiect_id,
        'angajat_id_filtru': angajat_id,
        'status_filtru': status_filtru,
    }


def get_daily_timesheet_rows(*, date_value, tenant_id=None):
    """Pontajele tenant-safe dintr-o zi, ca lista de dict-uri (ruta situatie_zilnica).

    Returneaza lista serializata identic cu ruta. Nu muteaza nimic.
    """
    pontaje = query_timesheets_for_tenant(tenant_id=tenant_id).filter_by(
        data=date_value
    ).order_by(Pontaj.angajat_id).all()
    result = []
    for p in pontaje:
        result.append({
            'angajat': p.angajat.nume_complet if p.angajat else '-',
            'proiect': p.proiect.cod_proiect if p.proiect else '-',
            'ora_start': p.ora_start or '-',
            'ora_sfarsit': p.ora_sfarsit or '-',
            'ore_lucrate': float(p.ore_lucrate) if p.ore_lucrate else 0,
            'tip_zi': p.tip_zi or '-',
            'status': p.status or '-'
        })
    return result


def get_timesheet_calendar_context(*, angajat_id, luna, anul, tenant_id=None):
    """Construieste contextul tenant-safe pentru calendarul lunar per angajat.

    Returneaza dict cu angajati, angajat, calendar_data, first_dow, stats, luna,
    anul, angajat_id. Nu muteaza nimic.
    """
    angajati = query_for_tenant(Angajat, tenant_id=tenant_id).filter_by(
        status='activ'
    ).order_by(Angajat.nume).all()

    angajat = None
    calendar_data = []
    stats = {'ore_normale': 0, 'ore_supl_50': 0, 'ore_supl_100': 0,
             'zile_lucrate': 0, 'zile_co': 0, 'zile_cm': 0, 'total_ore': 0}

    if angajat_id:
        angajat = query_for_tenant(Angajat, tenant_id=tenant_id).filter_by(id=angajat_id).first()
        _, days_in_month = calendar.monthrange(anul, luna)

        pontaje_luna = query_timesheets_for_tenant(tenant_id=tenant_id).filter(
            Pontaj.angajat_id == angajat_id,
            db.extract('month', Pontaj.data) == luna,
            db.extract('year', Pontaj.data) == anul
        ).all()

        pontaje_dict = {p.data: p for p in pontaje_luna}

        for day in range(1, days_in_month + 1):
            d = date(anul, luna, day)
            p = pontaje_dict.get(d)
            is_sarb = SarbatoareLegala.query.filter_by(data=d).first()
            dow = d.weekday()

            if p:
                if p.tip_zi == 'co':
                    tip = 'co'
                    stats['zile_co'] += 1
                elif p.tip_zi == 'cm':
                    tip = 'cm'
                    stats['zile_cm'] += 1
                elif p.tip_zi == 'invoiere':
                    tip = 'invoiere'
                else:
                    tip = 'prezent'
                    stats['zile_lucrate'] += 1
                stats['ore_normale'] += float(p.ore_normale or 0)
                stats['ore_supl_50'] += float(p.ore_suplimentare_50 or 0)
                stats['ore_supl_100'] += float(p.ore_suplimentare_100 or 0)
                stats['total_ore'] += float(p.ore_lucrate or 0)
            elif is_sarb:
                tip = 'sarbatoare'
            elif dow >= 5:
                tip = 'weekend'
            elif d > date.today():
                tip = 'viitor'
            else:
                tip = 'absent'

            calendar_data.append({
                'zi': day,
                'data': d,
                'dow': dow,
                'tip': tip,
                'pontaj': p,
                'is_today': d == date.today()
            })

        stats['ore_normale'] = round(stats['ore_normale'], 2)
        stats['ore_supl_50'] = round(stats['ore_supl_50'], 2)
        stats['ore_supl_100'] = round(stats['ore_supl_100'], 2)
        stats['total_ore'] = round(stats['total_ore'], 2)

    return {
        'angajati': angajati,
        'angajat': angajat,
        'angajat_id': angajat_id,
        'calendar_data': calendar_data,
        'first_dow': date(anul, luna, 1).weekday() if angajat_id else 0,
        'stats': stats,
        'luna': luna,
        'anul': anul,
    }


def get_timesheet_approval_context(*, filters, tenant_id=None):
    """Construieste contextul tenant-safe pentru pagina de aprobare (GET).

    `filters` are cheile: proiect_id, angajat_id, data_start, data_sfarsit.
    Returneaza dict cu pontaje (status trimis), proiecte, angajati si echourile
    de filtru. Permisiunea de manager ramane verificata in ruta. Nu muteaza nimic.
    """
    proiect_id = filters.get('proiect_id', '')
    angajat_id = filters.get('angajat_id', '')
    data_start = filters.get('data_start', '')
    data_sfarsit = filters.get('data_sfarsit', '')

    query = query_timesheets_for_tenant(tenant_id=tenant_id).filter_by(status='trimis')

    if proiect_id:
        query = query.filter(Pontaj.proiect_id == int(proiect_id))
    if angajat_id:
        query = query.filter(Pontaj.angajat_id == int(angajat_id))
    if data_start:
        query = query.filter(Pontaj.data >= datetime.strptime(data_start, '%Y-%m-%d').date())
    if data_sfarsit:
        query = query.filter(Pontaj.data <= datetime.strptime(data_sfarsit, '%Y-%m-%d').date())

    pontaje = query.order_by(Pontaj.data.desc()).all()

    proiecte = query_for_tenant(Proiect, tenant_id=tenant_id).filter(
        Proiect.status.in_(['activ', 'planificat'])
    ).order_by(Proiect.cod_proiect).all()
    angajati = query_for_tenant(Angajat, tenant_id=tenant_id).filter_by(
        status='activ'
    ).order_by(Angajat.nume).all()

    return {
        'pontaje': pontaje,
        'proiecte': proiecte,
        'angajati': angajati,
        'proiect_id_filtru': proiect_id,
        'angajat_id_filtru': angajat_id,
        'data_start': data_start,
        'data_sfarsit': data_sfarsit,
    }


def get_project_employees_for_timesheet(*, project_id, tenant_id=None):
    """Angajatii activi pe un proiect, tenant-safe (ruta angajati_proiect, AJAX).

    Proiectul este validat prin get_project_or_404 (id strain -> 404). Asocierile
    sunt filtrate, iar vizibilitatea angajatilor este impusa prin
    query_for_tenant(Angajat) (acelasi pattern indirect ca in T1.4). Returneaza
    o lista de dict-uri serializata identic cu ruta. Nu muteaza nimic.
    """
    get_project_or_404(project_id, tenant_id=tenant_id)
    asocieri = AngajatProiect.query.filter(
        AngajatProiect.proiect_id == project_id,
        (AngajatProiect.data_sfarsit.is_(None)) | (AngajatProiect.data_sfarsit >= date.today())
    ).all()

    angajat_ids = [ap.angajat_id for ap in asocieri]
    angajati_vizibili = set()
    if angajat_ids:
        angajati_vizibili = {
            a.id for a in query_for_tenant(Angajat, tenant_id=tenant_id).filter(
                Angajat.id.in_(angajat_ids)
            ).all()
        }

    result = []
    for ap in asocieri:
        if ap.angajat_id not in angajati_vizibili:
            continue
        a = ap.angajat
        result.append({
            'id': a.id,
            'nume_complet': a.nume_complet,
            'functie': ap.functie_pe_proiect or a.functie,
            'poza': a.poza_profil or '',
        })
    return result


def check_timesheet_duplicate(*, employee_id, date_value, exclude_timesheet_id=None,
                              tenant_id=None):
    """Verifica daca exista deja un pontaj pentru angajat in ziua respectiva.

    Tenant-safe: angajatul si pontajele sunt vazute prin helperi tenant-scoped,
    deci nu scurge pontaje din alt tenant. Returneaza un dict identic cu raspunsul
    rutei verificare_duplicat. Nu muteaza nimic.
    """
    if query_for_tenant(Angajat, tenant_id=tenant_id).filter_by(id=employee_id).first() is None:
        return {'exists': False}

    query = query_timesheets_for_tenant(tenant_id=tenant_id).filter_by(
        angajat_id=employee_id, data=date_value
    )
    if exclude_timesheet_id:
        query = query.filter(Pontaj.id != exclude_timesheet_id)

    existing = query.first()
    if existing:
        return {
            'exists': True,
            'proiect': existing.proiect.cod_proiect if existing.proiect else '-',
            'ore': float(existing.ore_lucrate) if existing.ore_lucrate else 0,
            'status': existing.status,
        }
    return {'exists': False}
