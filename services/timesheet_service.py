"""
EDIFICO WORKFORCE - Service layer pentru pontaje / timesheet (S1.2A).

Primul boundary de serviciu pentru domeniul Pontaj. Conform deciziei D015,
logica de timesheet traieste intr-un fisier NOU, separat de activity_service.

S1.2A extrage:
  * calculul pur de ore (calculate_timesheet_hours);
  * contextul de citire/listare tenant-safe pentru rutele GET/AJAX low-risk
    (lista, situatie zilnica, calendar angajat, aprobare GET, angajati pe
    proiect, verificare duplicat).

S1.2B1 adauga DOAR salvarea single create/edit:
  * adauga POST valid-save;
  * editeaza POST valid-save.

S1.2B2 adauga DOAR salvarea bulk create:
  * adauga_multiplu POST bulk-save.

S1.2C1 adauga DOAR workflow-ul single Pontaj:
  * trimite;
  * aproba;
  * respinge.

S1.2C2 adauga DOAR workflow-ul bulk Pontaj:
  * aproba_multiplu.

NU contine si nu trebuie sa contina in S1.2C2 (raman in rute, extrase ulterior
in S1.2D):
  * export/import (export_lunar, import_excel, template_import).

Toate query-urile pe date operationale tenant-owned folosesc helperii din
services/security/tenant_access.py. SarbatoareLegala este catalog global
(non-tenant) si ramane query direct, identic cu rutele de dinainte.

Serviciul este HTTP-free: fara flash/redirect/render_template/jsonify/request/
send_file. Pentru write-urile S1.2B1/S1.2B2, serviciul face commit; ruta face rollback
pe exceptii si pastreaza comportamentul HTTP vizibil.
"""

import calendar
from datetime import datetime, date

from werkzeug.exceptions import abort

from models import db, Pontaj, Angajat, Proiect, AngajatProiect, SarbatoareLegala
from services.security.tenant_access import (
    get_project_or_404,
    get_tenant_mode,
    query_for_tenant,
    query_timesheets_for_tenant,
    require_timesheet_inputs_same_tenant,
    tenant_id_for_new_record_or_403,
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
# S1.2B1 - salvare single create/edit (HTTP-free)
# ============================================================

def _field_data(form_data, name, default=None):
    """Citeste valoarea unui camp dintr-un PontajForm validat sau obiect similar."""
    if hasattr(form_data, name):
        field = getattr(form_data, name)
        return getattr(field, 'data', field)
    if hasattr(form_data, 'get'):
        return form_data.get(name, default)
    return default


def _as_date(value):
    if isinstance(value, date):
        return value
    if value:
        return datetime.strptime(str(value), '%Y-%m-%d').date()
    return value


def _timesheet_values_from_form_data(form_data):
    data_pontaj = _as_date(_field_data(form_data, 'data'))
    tip_zi = _field_data(form_data, 'tip_zi') or 'lucratoare'
    return {
        'angajat_id': _field_data(form_data, 'angajat_id'),
        'proiect_id': _field_data(form_data, 'proiect_id'),
        'data': data_pontaj,
        'ora_start': _field_data(form_data, 'ora_start'),
        'ora_sfarsit': _field_data(form_data, 'ora_sfarsit'),
        'tip_zi': tip_zi,
        'observatii': _field_data(form_data, 'observatii') or '',
        'actiune': _field_data(form_data, 'actiune') or 'draft',
    }


def _tenant_id_for_timesheet_write(tenant_id):
    if tenant_id is not None:
        return tenant_id
    return tenant_id_for_new_record_or_403()


def _validate_timesheet_inputs(values, *, tenant_id=None):
    tenant_id_curent = _tenant_id_for_timesheet_write(tenant_id)
    require_timesheet_inputs_same_tenant(
        proiect_id=values['proiect_id'],
        angajat_id=values['angajat_id'],
        tenant_id=tenant_id_curent,
    )
    return tenant_id_curent


def _find_timesheet_duplicate(*, employee_id, date_value, exclude_timesheet_id=None,
                              tenant_id=None):
    query = query_timesheets_for_tenant(tenant_id=tenant_id).filter_by(
        angajat_id=employee_id,
        data=date_value,
    )
    if exclude_timesheet_id:
        query = query.filter(Pontaj.id != exclude_timesheet_id)
    return query.first()


def _apply_timesheet_values(pontaj, values):
    result = calculate_timesheet_hours(
        ora_start=values['ora_start'],
        ora_sfarsit=values['ora_sfarsit'],
        tip_zi=values['tip_zi'],
        data_pontaj=values['data'],
    )
    pontaj.angajat_id = values['angajat_id']
    pontaj.proiect_id = values['proiect_id']
    pontaj.data = values['data']
    pontaj.ora_start = values['ora_start']
    pontaj.ora_sfarsit = values['ora_sfarsit']
    pontaj.ore_lucrate = result['ore_lucrate']
    pontaj.ore_normale = result['ore_normale']
    pontaj.ore_suplimentare_50 = result['ore_supl_50']
    pontaj.ore_suplimentare_100 = result['ore_supl_100']
    pontaj.tip_zi = result['tip_zi']
    pontaj.observatii = values['observatii']
    return result


def create_timesheet_from_form_data(*, form_data, current_user, tenant_id=None):
    """Creeaza un Pontaj single din PontajForm validat.

    Ruta ramane responsabila pentru PontajForm, validate_on_submit(), flash,
    render si redirect. Serviciul pastreaza tenant validation, duplicate check,
    calcul ore, asignare campuri si commit. La duplicat nu muteaza si nu comite.
    """
    values = _timesheet_values_from_form_data(form_data)
    tenant_id_curent = _validate_timesheet_inputs(values, tenant_id=tenant_id)

    duplicate = _find_timesheet_duplicate(
        employee_id=values['angajat_id'],
        date_value=values['data'],
        tenant_id=tenant_id_curent,
    )
    if duplicate:
        return {'timesheet': duplicate, 'created': False, 'duplicate': True,
                'action': values['actiune']}

    status = 'trimis' if values['actiune'] == 'trimite' else 'draft'
    pontaj = Pontaj(status=status, introdus_de=getattr(current_user, 'id', None))
    _apply_timesheet_values(pontaj, values)
    db.session.add(pontaj)
    db.session.commit()
    return {'timesheet': pontaj, 'created': True, 'duplicate': False,
            'action': values['actiune']}


def update_timesheet_from_form_data(*, timesheet, form_data, current_user=None,
                                    tenant_id=None):
    """Actualizeaza un Pontaj single existent din PontajForm validat.

    Nu incarca obiectul dupa ID; ruta pastreaza `get_timesheet_or_404(id)`.
    Statusul se schimba doar pentru actiune == 'trimite'; altfel ramane exact
    statusul curent (draft/respins), ca in ruta veche.
    """
    values = _timesheet_values_from_form_data(form_data)
    tenant_id_curent = _validate_timesheet_inputs(values, tenant_id=tenant_id)

    duplicate = _find_timesheet_duplicate(
        employee_id=values['angajat_id'],
        date_value=values['data'],
        exclude_timesheet_id=timesheet.id,
        tenant_id=tenant_id_curent,
    )
    if duplicate:
        return {'timesheet': timesheet, 'duplicate_timesheet': duplicate,
                'updated': False, 'duplicate': True, 'action': values['actiune']}

    _apply_timesheet_values(timesheet, values)
    if values['actiune'] == 'trimite':
        timesheet.status = 'trimis'

    db.session.commit()
    return {'timesheet': timesheet, 'updated': True, 'duplicate': False,
            'action': values['actiune']}


# ============================================================
# S1.2B2 - salvare bulk create (HTTP-free)
# ============================================================

def _required_form_value(form_data, name):
    if hasattr(form_data, '__getitem__'):
        return form_data[name]
    return _field_data(form_data, name)


def _form_values_list(form_data, name):
    if hasattr(form_data, 'getlist'):
        return form_data.getlist(name)
    value = _field_data(form_data, name, [])
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _bulk_timesheet_values_from_form_data(form_data):
    proiect_id = int(_required_form_value(form_data, 'proiect_id'))
    data_pontaj = _as_date(_required_form_value(form_data, 'data'))
    actiune = _field_data(form_data, 'actiune', 'draft') or 'draft'
    angajat_ids = _form_values_list(form_data, 'angajat_ids')

    return {
        'proiect_id': proiect_id,
        'data': data_pontaj,
        'actiune': actiune,
        'angajat_ids': angajat_ids,
    }


def _bulk_timesheet_rows_from_form_data(form_data, angajat_ids):
    randuri = []
    for aid_str in angajat_ids:
        aid = int(aid_str)
        randuri.append({
            'angajat_id': aid,
            'ora_start': _field_data(form_data, f'ora_start_{aid}', '08:00'),
            'ora_sfarsit': _field_data(form_data, f'ora_sfarsit_{aid}', '16:00'),
            'tip_zi': _field_data(form_data, f'tip_zi_{aid}', 'lucratoare'),
            'observatii': (_field_data(form_data, f'observatii_{aid}', '') or '').strip(),
        })
    return randuri


def create_multiple_timesheets_from_form_data(*, form_data, current_user,
                                              tenant_id=None):
    """Creeaza pontaje bulk din formularul adauga_multiplu.

    Ruta ramane responsabila pentru flash/redirect/render. Serviciul pastreaza
    validarea tenant-safe, skip-ul de duplicate, asignarea campurilor si commit-ul
    unic dupa loop. La eroare de tenant/parsare nu creeaza randuri.
    """
    values = _bulk_timesheet_values_from_form_data(form_data)
    tenant_id_curent = _tenant_id_for_timesheet_write(tenant_id)
    for aid_str in values['angajat_ids']:
        require_timesheet_inputs_same_tenant(
            proiect_id=values['proiect_id'],
            angajat_id=aid_str,
            tenant_id=tenant_id_curent,
        )
    randuri = _bulk_timesheet_rows_from_form_data(form_data, values['angajat_ids'])

    count_ok = 0
    count_skip = 0
    created_timesheets = []
    status = 'trimis' if values['actiune'] == 'trimite' else 'draft'

    for rand in randuri:
        duplicate = _find_timesheet_duplicate(
            employee_id=rand['angajat_id'],
            date_value=values['data'],
            tenant_id=tenant_id_curent,
        )
        if duplicate:
            count_skip += 1
            continue

        result = calculate_timesheet_hours(
            ora_start=rand['ora_start'],
            ora_sfarsit=rand['ora_sfarsit'],
            tip_zi=rand['tip_zi'],
            data_pontaj=values['data'],
        )
        pontaj = Pontaj(
            angajat_id=rand['angajat_id'],
            proiect_id=values['proiect_id'],
            data=values['data'],
            ora_start=rand['ora_start'],
            ora_sfarsit=rand['ora_sfarsit'],
            ore_lucrate=result['ore_lucrate'],
            ore_normale=result['ore_normale'],
            ore_suplimentare_50=result['ore_supl_50'],
            ore_suplimentare_100=result['ore_supl_100'],
            tip_zi=result['tip_zi'],
            status=status,
            observatii=rand['observatii'],
            introdus_de=getattr(current_user, 'id', None),
        )
        db.session.add(pontaj)
        created_timesheets.append(pontaj)
        count_ok += 1

    db.session.commit()
    return {
        'created_count': count_ok,
        'skipped_count': count_skip,
        'created_timesheets': created_timesheets,
        'action': values['actiune'],
    }


# ============================================================
# S1.2C1 - workflow single Pontaj (HTTP-free)
# ============================================================

def submit_timesheet_for_approval(*, timesheet):
    """Tranzitie draft -> trimis pentru un Pontaj deja incarcat tenant-safe.

    Ruta pastreaza `get_timesheet_or_404(id)`, flash si redirect. Daca pontajul
    nu este in `draft`, comportamentul ramane no-op fara commit.
    """
    if timesheet.status != 'draft':
        return {'timesheet': timesheet, 'changed': False, 'submitted': False}

    timesheet.status = 'trimis'
    db.session.commit()
    return {'timesheet': timesheet, 'changed': True, 'submitted': True}


def approve_timesheet(*, timesheet, current_user):
    """Aproba un Pontaj deja incarcat tenant-safe.

    Pastreaza comportamentul existent: fara preconditie de status, seteaza
    statusul, utilizatorul aprobator si data aprobarii, apoi face commit.
    """
    timesheet.status = 'aprobat'
    timesheet.aprobat_de = getattr(current_user, 'id', None)
    timesheet.data_aprobare = datetime.utcnow()
    db.session.commit()
    return {'timesheet': timesheet, 'changed': True, 'approved': True}


def reject_timesheet(*, timesheet, current_user, reason):
    """Respinge un Pontaj deja incarcat tenant-safe.

    `reason` este citit in ruta din formular si este salvat exact asa cum vine,
    inclusiv sir gol, ca in comportamentul existent.
    """
    timesheet.status = 'respins'
    timesheet.motiv_respingere = reason
    timesheet.aprobat_de = getattr(current_user, 'id', None)
    timesheet.data_aprobare = datetime.utcnow()
    db.session.commit()
    return {'timesheet': timesheet, 'changed': True, 'rejected': True}


# ============================================================
# S1.2C2 - workflow bulk Pontaj (HTTP-free)
# ============================================================

def bulk_approve_timesheets(*, ids, current_user, tenant_id=None):
    """Aproba in masa Pontajele trimise, selectate prin lista de ID-uri.

    S1.2C2 extrage logica de domeniu din routes/pontaje.py::aproba_multiplu.

    Ramura off-mode: query direct prin id (T1.4 legacy, identic cu aproba_masa
    din activitati). Permis EXCLUSIV in aceasta ramura izolata.
    Skipuieste silentios IDs lipsa si pontaje non-trimis.

    Ramura tenant-aware: valideaza TOATE ID-urile inainte de orice mutatie
    (fail-all). ID-uri lipsa sau din alt tenant duc la abort(404) fara nicio
    scriere in baza de date.

    Returneaza {'approved_count': int, 'timesheets': list[Pontaj]}.
    """
    if get_tenant_mode() == 'off':
        # Ramura legacy off-mode: query direct prin id permis (T1.4 pattern).
        # ValueError propagat ca in ruta originala daca pid_str nu e numeric.
        pontaje = []
        for pid_str in ids:
            pontaj = Pontaj.query.get(int(pid_str))
            if pontaj and pontaj.status == 'trimis':
                pontaje.append(pontaj)
    else:
        try:
            ids_int = [int(pid_str) for pid_str in ids]
        except (TypeError, ValueError):
            ids_int = []
        ids_int = [pid for pid in ids_int if pid > 0]
        if len(ids_int) != len(ids) or not ids_int:
            abort(404)
        pontaje = query_timesheets_for_tenant(tenant_id=tenant_id).filter(
            Pontaj.id.in_(ids_int)
        ).all()
        if len({p.id for p in pontaje}) != len(set(ids_int)):
            abort(404)
        pontaje = [p for p in pontaje if p.status == 'trimis']

    count = 0
    for pontaj in pontaje:
        pontaj.status = 'aprobat'
        pontaj.aprobat_de = current_user.id
        pontaj.data_aprobare = datetime.utcnow()
        count += 1

    db.session.commit()
    return {'approved_count': count, 'timesheets': pontaje}


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


# ============================================================
# Asamblare date export lunar (read-only)
# ============================================================

def build_monthly_timesheet_export_data(*, month, year, project_id=0, tenant_id=None):
    """Asambleaza datele tenant-safe pentru exportul Excel lunar (ruta export_lunar).

    S1.2D1 extrage DOAR partea de query/grupare/asamblare date din
    routes/pontaje.py::export_lunar. Construirea workbook-ului (foi, stiluri,
    formule, send_file, nume fisier) ramane integral in ruta.

    Tenant-safe: pontajele sunt vazute prin query_timesheets_for_tenant(); un
    project_id strain este respins prin get_project_or_404 (-> 404). SarbatoareLegala
    este catalog global (non-tenant), interogat la fel ca in ruta. Read-only:
    nu adauga, nu muteaza, nu face commit.

    Returneaza un dict cu cheile asteptate de ruta pentru layout:
    pontaje, angajat_data, sorted_angajati, sarbatori, proiect_export.
    """
    query = query_timesheets_for_tenant(tenant_id=tenant_id).filter(
        db.extract('month', Pontaj.data) == month,
        db.extract('year', Pontaj.data) == year
    )
    proiect_export = None
    if project_id:
        proiect_export = get_project_or_404(project_id, tenant_id=tenant_id)
        query = query.filter(Pontaj.proiect_id == project_id)

    pontaje = query.all()

    # Grupare pe angajat (identic cu ruta veche)
    angajat_data = {}
    for p in pontaje:
        if p.angajat_id not in angajat_data:
            angajat_data[p.angajat_id] = {
                'angajat': p.angajat,
                'zile': {},
                'total_ore': 0,
                'ore_normale': 0,
                'ore_supl_50': 0,
                'ore_supl_100': 0
            }
        ad = angajat_data[p.angajat_id]
        ad['zile'][p.data.day] = p
        ad['total_ore'] += float(p.ore_lucrate or 0)
        ad['ore_normale'] += float(p.ore_normale or 0)
        ad['ore_supl_50'] += float(p.ore_suplimentare_50 or 0)
        ad['ore_supl_100'] += float(p.ore_suplimentare_100 or 0)

    # Sarbatori legale ale lunii (catalog global)
    sarbatori = {s.data.day for s in SarbatoareLegala.query.filter(
        db.extract('month', SarbatoareLegala.data) == month,
        db.extract('year', SarbatoareLegala.data) == year
    ).all()}

    sorted_angajati = sorted(angajat_data.values(), key=lambda x: x['angajat'].nume_complet)

    return {
        'pontaje': pontaje,
        'angajat_data': angajat_data,
        'sorted_angajati': sorted_angajati,
        'sarbatori': sarbatori,
        'proiect_export': proiect_export,
    }
