"""
EDIFICO WORKFORCE - Service layer pentru activitati (S1.1A).

Acest modul reprezinta primul boundary de serviciu pentru domeniul activitati.
El extrage DOAR logica de CITIRE si CONTEXT-FORMULAR tenant-safe din
routes/activitati.py:

  * contextul panoului de activitati (dashboard + filtre + dropdown-uri);
  * contextul de dropdown pentru formularul de creare/editare;
  * rezolvarea angajatului asociat utilizatorului logat (read-context);
  * incarcarea optiunilor de context BIM pentru panou/formular.

NU contine si nu trebuie sa contina (raman in rute, extrase ulterior in
S1.1B/C/D):

  * logica de salvare create/edit (_salveaza_activitate);
  * tranzitiile de workflow (trimite/aproba/respinge/aprobare_masa);
  * generarea de rapoarte/exporturi (raport_*, export_*).

Toate query-urile pe date operationale tenant-owned (activitati, proiecte,
angajati, context BIM) folosesc helperii din services/security/tenant_access.py,
niciodata query brut pe modele. Cataloagele globale de configurare
(TipInstalatie, CategorieActivitate, SarbatoareLegala) nu sunt date tenant-owned
si raman query-uri directe, identic cu rutele de dinainte.

Comportamentul pe moduri (off/optional/strict) este pastrat identic cu rutele:
helperii tenant-safe primesc tenant_id (sau None pentru auto-rezolvare din
request context) si aplica regulile de scoping deja stabilite in T1.x.
"""

import calendar
import json
from datetime import datetime, date, timedelta
from decimal import Decimal

from flask import abort

from models import (
    db, Angajat, Proiect, Pontaj, TipInstalatie, CategorieActivitate,
    RaportActivitate, Santier, Cladire, ElementBIM, SarbatoareLegala,
)
from services.security.tenant_access import (
    get_activity_or_404,
    get_project_or_404,
    get_tenant_mode,
    query_activities_for_tenant,
    query_bim_buildings_for_tenant,
    query_bim_elements_for_tenant,
    query_sites_for_tenant,
    query_timesheets_for_tenant,
    query_for_tenant,
    require_activity_inputs_same_tenant,
    require_activity_bim_context_same_tenant,
    tenant_id_for_new_record_or_403,
)


class ActivityValidationError(Exception):
    """Validare de business esuata la salvarea activitatii (camp obligatoriu lipsa).

    Ruta o transforma in flash + redirect(request.url), pastrand comportamentul
    existent. Nu este o eroare de tenant (acelea raman HTTPException/abort).
    """

    def __init__(self, message):
        super().__init__(message)
        self.message = message


def get_current_employee_for_user(*, current_user, tenant_id=None):
    """Angajatul activ asociat utilizatorului logat (dupa email), tenant-safe.

    Read-context: oglindeste exact lookup-ul folosit anterior in ruta
    (_get_angajat_for_user). Returneaza None daca userul nu are email sau nu
    exista angajat corespunzator vizibil tenantului curent.
    """
    if current_user and getattr(current_user, 'email', None):
        return (
            query_for_tenant(Angajat, tenant_id=tenant_id)
            .filter_by(email=current_user.email, status='activ')
            .first()
        )
    return None


def _zile_lucratoare(an, luna):
    """Numarul de zile lucratoare din luna (Luni-Vineri minus sarbatori legale).

    Mutat din routes/activitati.py::_get_zile_lucratoare (singurul apelant era
    panoul). SarbatoareLegala este catalog global, nu date tenant-owned.
    """
    sarbatori = set()
    for s in SarbatoareLegala.query.filter_by(an=an).all():
        if s.data.month == luna:
            sarbatori.add(s.data.day)

    cal = calendar.monthcalendar(an, luna)
    zile = 0
    for week in cal:
        for i in range(5):  # Luni-Vineri
            day = week[i]
            if day != 0 and day not in sarbatori:
                zile += 1
    return zile


def get_activity_panel_context(*, filters, current_user, tenant_id=None):
    """Construieste contextul tenant-safe pentru panoul de activitati.

    `filters` este un dict cu cheile din query string-ul rutei panou:
    angajat_id, proiect_id, tip_instalatie_id, status, tip, status_executie,
    data_start, data_end, santier_id, cladire_id, element_bim_id, tip_element.

    Returneaza un dict gata de pasat ca **kwargs catre templateul
    activitati/panou.html. Nu muteaza nimic.
    """
    today = date.today()
    angajat_curent = get_current_employee_for_user(
        current_user=current_user, tenant_id=tenant_id
    )

    # Date personale
    activitate_azi = None
    activitati_saptamana = []
    activitati_luna = []
    zile_cu_activitate_sapt = 0
    zile_cu_activitate_luna = 0
    zile_lucratoare_luna = _zile_lucratoare(today.year, today.month)
    proiecte_saptamana = set()
    activitati_aprobate_luna = 0
    activitati_pending_luna = 0

    if angajat_curent:
        # Activitate azi
        activitate_azi = query_activities_for_tenant(tenant_id=tenant_id).filter_by(
            angajat_id=angajat_curent.id, data=today
        ).first()

        # Saptamana curenta
        luni = today - timedelta(days=today.weekday())
        duminica = luni + timedelta(days=6)
        activitati_saptamana = query_activities_for_tenant(tenant_id=tenant_id).filter(
            RaportActivitate.angajat_id == angajat_curent.id,
            RaportActivitate.data >= luni,
            RaportActivitate.data <= duminica
        ).all()
        zile_cu_activitate_sapt = len(set(a.data for a in activitati_saptamana))
        proiecte_saptamana = set(a.proiect_id for a in activitati_saptamana)

        # Luna curenta
        prima_zi = today.replace(day=1)
        activitati_luna = query_activities_for_tenant(tenant_id=tenant_id).filter(
            RaportActivitate.angajat_id == angajat_curent.id,
            RaportActivitate.data >= prima_zi,
            RaportActivitate.data <= today
        ).all()
        zile_cu_activitate_luna = len(set(a.data for a in activitati_luna))
        activitati_aprobate_luna = sum(1 for a in activitati_luna if a.status == 'aprobat')
        activitati_pending_luna = sum(1 for a in activitati_luna if a.status in ('draft', 'trimis'))

    # Tabel activitati recente (manageri vad tot, operatorii doar ale lor)
    query = query_activities_for_tenant(tenant_id=tenant_id)

    # Filtre
    f_angajat = filters.get('angajat_id')
    f_proiect = filters.get('proiect_id')
    f_instalatie = filters.get('tip_instalatie_id')
    f_status = filters.get('status', '')
    f_tip = filters.get('tip', '')  # tip_activitate: zilnica/saptamanala/lunara
    f_status_executie = filters.get('status_executie', '')
    f_data_start = filters.get('data_start', '')
    f_data_end = filters.get('data_end', '')
    # Filtre BIM
    f_santier = filters.get('santier_id')
    f_cladire = filters.get('cladire_id')
    f_element_bim = filters.get('element_bim_id')
    f_tip_element = filters.get('tip_element', '')

    if current_user.rol == 'operator' and angajat_curent:
        query = query.filter_by(angajat_id=angajat_curent.id)
    elif current_user.rol == 'operator':
        query = query.filter_by(id=-1)  # no results

    if f_angajat:
        query = query.filter_by(angajat_id=f_angajat)
    if f_proiect:
        query = query.filter_by(proiect_id=f_proiect)
    if f_instalatie:
        query = query.filter_by(tip_instalatie_id=f_instalatie)
    if f_status:
        query = query.filter_by(status=f_status)
    if f_tip in ('zilnica', 'saptamanala', 'lunara'):
        query = query.filter_by(tip_activitate=f_tip)
    if f_status_executie in ('planificata', 'in_desfasurare', 'finalizata'):
        query = query.filter_by(status_executie=f_status_executie)
    if f_data_start:
        try:
            ds = datetime.strptime(f_data_start, '%Y-%m-%d').date()
            query = query.filter(RaportActivitate.data >= ds)
        except ValueError:
            pass
    if f_data_end:
        try:
            de = datetime.strptime(f_data_end, '%Y-%m-%d').date()
            query = query.filter(RaportActivitate.data <= de)
        except ValueError:
            pass

    # Filtre BIM: aplicate peste subquery tenant-safe ca ID-urile straine sa nu scurga date.
    if f_element_bim or f_tip_element or f_cladire or f_santier:
        elemente_query = query_bim_elements_for_tenant(tenant_id=tenant_id)
        if f_element_bim:
            elemente_query = elemente_query.filter(ElementBIM.id == f_element_bim)
        if f_tip_element:
            elemente_query = elemente_query.filter(ElementBIM.tip_element == f_tip_element)
        if f_cladire:
            elemente_query = elemente_query.filter(ElementBIM.cladire_id == f_cladire)
        if f_santier:
            elemente_query = elemente_query.filter(
                ElementBIM.cladire.has(Cladire.santier_id == f_santier)
            )
        query = query.filter(
            RaportActivitate.element_bim_id.in_(elemente_query.with_entities(ElementBIM.id))
        )

    activitati_recente = query.order_by(
        RaportActivitate.data.desc(), RaportActivitate.introdus_la.desc()
    ).limit(50).all()

    # Aprobare count (pentru manageri)
    pending_aprobare = 0
    if current_user.rol in ('admin', 'manager'):
        pending_aprobare = query_activities_for_tenant(tenant_id=tenant_id).filter_by(
            status='trimis'
        ).count()

    # Dropdown-uri filtre
    angajati = query_for_tenant(Angajat, tenant_id=tenant_id).filter_by(
        status='activ'
    ).order_by(Angajat.nume).all()
    proiecte = query_for_tenant(Proiect, tenant_id=tenant_id).filter(
        Proiect.status.in_(['activ', 'planificat'])
    ).order_by(Proiect.cod_proiect).all()
    instalatii = TipInstalatie.query.filter_by(activ=True).order_by(TipInstalatie.ordine).all()
    bim_santiere = query_sites_for_tenant(tenant_id=tenant_id).order_by(Santier.cod).all()
    bim_cladiri = query_bim_buildings_for_tenant(tenant_id=tenant_id).order_by(Cladire.cod).all()
    bim_tipuri_element = ElementBIM.TIPURI

    return {
        'today': today,
        'angajat_curent': angajat_curent,
        'activitate_azi': activitate_azi,
        'activitati_saptamana': activitati_saptamana,
        'zile_cu_activitate_sapt': zile_cu_activitate_sapt,
        'proiecte_saptamana': proiecte_saptamana,
        'activitati_luna': activitati_luna,
        'zile_cu_activitate_luna': zile_cu_activitate_luna,
        'zile_lucratoare_luna': zile_lucratoare_luna,
        'activitati_aprobate_luna': activitati_aprobate_luna,
        'activitati_pending_luna': activitati_pending_luna,
        'activitati_recente': activitati_recente,
        'pending_aprobare': pending_aprobare,
        'angajati': angajati,
        'proiecte': proiecte,
        'instalatii': instalatii,
        'f_angajat': f_angajat,
        'f_proiect': f_proiect,
        'f_instalatie': f_instalatie,
        'f_status': f_status,
        'f_tip': f_tip,
        'f_status_executie': f_status_executie,
        'f_data_start': f_data_start,
        'f_data_end': f_data_end,
        'bim_santiere': bim_santiere,
        'bim_cladiri': bim_cladiri,
        'bim_tipuri_element': bim_tipuri_element,
        'f_santier': f_santier,
        'f_cladire': f_cladire,
        'f_element_bim': f_element_bim,
        'f_tip_element': f_tip_element,
    }


def get_activity_form_context(*, activity=None, current_user=None, tenant_id=None):
    """Dropdown-uri tenant-safe pentru formularul de creare/editare activitate.

    Cele cinci liste de optiuni (angajati, proiecte, instalatii, categorii,
    santiere) sunt identice pentru adaugare (activity=None) si editare
    (activity=<RaportActivitate>) si nu depind de utilizatorul curent; parametrii
    `activity` si `current_user` sunt acceptati pentru claritate si simetrie cu
    contextul de panou si nu modifica rezultatul in S1.1A.

    Returneaza un dict cu cheile: angajati, proiecte, instalatii, categorii,
    santiere. Nu muteaza nimic.
    """
    return {
        'angajati': query_for_tenant(Angajat, tenant_id=tenant_id).filter_by(
            status='activ'
        ).order_by(Angajat.nume).all(),
        'proiecte': query_for_tenant(Proiect, tenant_id=tenant_id).filter(
            Proiect.status.in_(['activ', 'planificat'])
        ).order_by(Proiect.cod_proiect).all(),
        'instalatii': TipInstalatie.query.filter_by(activ=True).order_by(
            TipInstalatie.ordine
        ).all(),
        'categorii': CategorieActivitate.query.filter_by(activa=True).order_by(
            CategorieActivitate.ordine
        ).all(),
        'santiere': query_sites_for_tenant(tenant_id=tenant_id).order_by(Santier.cod).all(),
    }


def save_activity_from_form_data(*, activity=None, form_data, current_user=None, tenant_id=None):
    """Orchestreaza salvarea (create/edit) unei activitati din datele formularului.

    Mutat din routes/activitati.py::_salveaza_activitate (corpul try). Pastreaza
    identic: parsarea/sanitizarea campurilor, validarile tenant-safe, atribuirea
    campurilor pe RaportActivitate, serializarea JSON, derivarea zonei din spatiu,
    statusul inline pe salvare si calculeaza_perioada().

    `form_data` este un MultiDict (de regula request.form). Nu atinge HTTP:
    - campurile obligatorii lipsa ridica ActivityValidationError (ruta o
      transforma in flash + redirect);
    - ID-urile straine (proiect/angajat/BIM) ridica HTTPException prin helperii
      tenant-safe, inainte de orice mutatie;
    - commit-ul este facut aici; rollback-ul ramane in responsabilitatea rutei.

    Returneaza un dict {'activity': <RaportActivitate>, 'actiune': <str>} pe care
    ruta il foloseste ca sa aleaga flash-ul, redirect-ul sau raspunsul JSON.
    """
    angajat_id = form_data.get('angajat_id', type=int)
    # Multi-proiect: accepta atat 'proiect_ids[]' (multi) cat si 'proiect_id' (legacy)
    proiect_ids_raw = form_data.getlist('proiect_ids[]') or form_data.getlist('proiect_ids')
    proiecte_ids_clean = []
    for v in proiect_ids_raw:
        try:
            n = int(v)
            if n > 0 and n not in proiecte_ids_clean:
                proiecte_ids_clean.append(n)
        except (ValueError, TypeError):
            continue
    if not proiecte_ids_clean:
        # Fallback la single proiect_id (forma veche)
        single = form_data.get('proiect_id', type=int)
        if single:
            proiecte_ids_clean = [single]
    proiect_id = proiecte_ids_clean[0] if proiecte_ids_clean else None
    proiecte_json = json.dumps(proiecte_ids_clean) if proiecte_ids_clean else None
    data_str = form_data.get('data', '')
    data_sfarsit_str = form_data.get('data_sfarsit', '').strip()
    tip_activitate = form_data.get('tip_activitate', 'zilnica').strip() or 'zilnica'
    if tip_activitate not in ('zilnica', 'saptamanala', 'lunara'):
        tip_activitate = 'zilnica'
    supervisor_id = form_data.get('supervisor_id', type=int) or None
    subordonati_raw = form_data.getlist('subordonati_ids[]') or form_data.getlist('subordonati_ids')
    ore_lucrate_str = form_data.get('ore_lucrate', '').strip()
    status_executie = form_data.get('status_executie', 'planificata').strip() or 'planificata'
    if status_executie not in ('planificata', 'in_desfasurare', 'finalizata'):
        status_executie = 'planificata'
    tip_instalatie_id = form_data.get('tip_instalatie_id', type=int) or None
    categorie_id = form_data.get('categorie_activitate_id', type=int) or None
    zona_lucru = form_data.get('zona_lucru', '').strip()
    activitate_principala = form_data.get('activitate_principala', '').strip()
    activitate_detaliata = form_data.get('activitate_detaliata', '').strip()
    cantitate = form_data.get('cantitate_executata', '')
    um = form_data.get('unitate_masura', '').strip()
    procent = form_data.get('procent_realizare', type=int)
    probleme = form_data.get('probleme_intampinate', '').strip()
    solutii = form_data.get('solutii_aplicate', '').strip()
    observatii = form_data.get('observatii', '').strip()
    necesita_aprobare = bool(form_data.get('necesita_aprobare_tehnica'))
    include_sambata = bool(form_data.get('include_sambata'))
    include_duminica = bool(form_data.get('include_duminica'))
    actiune = form_data.get('actiune', 'draft')  # draft / trimite / alta

    # BIM context (toate optionale)
    bim_santier_id = form_data.get('bim_santier_id', type=int) or None
    bim_cladire_id = form_data.get('bim_cladire_id', type=int) or None
    bim_nivel_id = form_data.get('bim_nivel_id', type=int) or None
    bim_element_id = form_data.get('bim_element_id', type=int) or None
    bim_spatiu_id = form_data.get('bim_spatiu_id', type=int) or None
    # Zona se ia din spatiu daca exista, altfel din formular
    bim_zona_id = form_data.get('bim_zona_id', type=int) or None

    # Detalii pe zi (pentru saptamanala/lunara): liste paralele
    det_data_list = form_data.getlist('detaliu_data[]')
    det_proiect_list = form_data.getlist('detaliu_proiect[]')
    det_text_list = form_data.getlist('detaliu_text[]')
    det_ore_list = form_data.getlist('detaliu_ore[]')

    # Validare
    if not angajat_id or not proiect_id:
        raise ActivityValidationError('Angajatul si cel putin un proiect sunt obligatorii.')
    if not activitate_principala:
        raise ActivityValidationError('Titlul activitatii este obligatoriu.')
    if not data_str:
        raise ActivityValidationError('Data de inceput este obligatorie.')

    data_val = datetime.strptime(data_str, '%Y-%m-%d').date()
    data_sfarsit_val = None
    if data_sfarsit_str:
        try:
            data_sfarsit_val = datetime.strptime(data_sfarsit_str, '%Y-%m-%d').date()
        except ValueError:
            data_sfarsit_val = None

    # subordonati_ids - parseaza si curata
    subordonati_ids_clean = []
    for raw_val in subordonati_raw:
        try:
            v = int(raw_val)
            if v != angajat_id and v not in subordonati_ids_clean:
                subordonati_ids_clean.append(v)
        except (ValueError, TypeError):
            continue
    subordonati_json = json.dumps(subordonati_ids_clean) if subordonati_ids_clean else None

    # ore lucrate
    try:
        ore_lucrate_val = Decimal(ore_lucrate_str) if ore_lucrate_str else None
    except (ValueError, TypeError):
        ore_lucrate_val = None

    # Materiale JSON
    materiale_json = '[]'
    mat_denumiri = form_data.getlist('mat_denumire[]')
    mat_cantitati = form_data.getlist('mat_cantitate[]')
    mat_um = form_data.getlist('mat_um[]')
    if mat_denumiri:
        materiale = []
        for i in range(len(mat_denumiri)):
            if mat_denumiri[i].strip():
                materiale.append({
                    'denumire': mat_denumiri[i].strip(),
                    'cantitate': mat_cantitati[i].strip() if i < len(mat_cantitati) else '',
                    'um': mat_um[i].strip() if i < len(mat_um) else ''
                })
        materiale_json = json.dumps(materiale, ensure_ascii=False)

    # Construire JSON detalii pe zi (doar randuri cu macar un camp completat)
    detalii_json = None
    detalii_proiect_ids = []
    if tip_activitate in ('saptamanala', 'lunara') and det_data_list:
        detalii_curate = []
        for i, d_str in enumerate(det_data_list):
            d_str = (d_str or '').strip()
            if not d_str:
                continue
            proi_str = det_proiect_list[i] if i < len(det_proiect_list) else ''
            text = (det_text_list[i] if i < len(det_text_list) else '').strip()
            ore_str = (det_ore_list[i] if i < len(det_ore_list) else '').strip()
            # Sare peste randuri complet goale (dar pastreaza data ca placeholder)
            if not text and not ore_str and not proi_str:
                continue
            item = {'data': d_str}
            if proi_str:
                try:
                    item['proiect_id'] = int(proi_str)
                    detalii_proiect_ids.append(item['proiect_id'])
                except (ValueError, TypeError):
                    pass
            if text:
                item['text'] = text[:500]
            if ore_str:
                try:
                    item['ore'] = float(ore_str)
                except (ValueError, TypeError):
                    pass
            detalii_curate.append(item)
        if detalii_curate:
            detalii_json = json.dumps(detalii_curate, ensure_ascii=False)

    echipamente = form_data.get('echipamente_folosite', '').strip()

    tenant_id_curent = tenant_id_for_new_record_or_403()
    angajat_ids_de_validat = [angajat_id]
    if supervisor_id:
        angajat_ids_de_validat.append(supervisor_id)
    angajat_ids_de_validat.extend(subordonati_ids_clean)
    require_activity_inputs_same_tenant(
        proiecte_ids_clean + detalii_proiect_ids,
        angajat_ids=angajat_ids_de_validat,
        tenant_id=tenant_id_curent,
    )
    bim_context = require_activity_bim_context_same_tenant(
        santier_id=bim_santier_id,
        cladire_id=bim_cladire_id,
        nivel_id=bim_nivel_id,
        zona_id=bim_zona_id,
        spatiu_id=bim_spatiu_id,
        element_bim_id=bim_element_id,
        proiect_id=proiect_id,
        tenant_id=tenant_id_curent,
    )
    if not bim_zona_id and bim_context.get('spatiu'):
        bim_zona_id = getattr(bim_context['spatiu'], 'zona_id', None)

    if activity is None:
        activity = RaportActivitate()
        db.session.add(activity)

    activity.angajat_id = angajat_id
    activity.proiect_id = proiect_id
    activity.proiecte_ids = proiecte_json
    activity.element_bim_id = bim_element_id
    activity.spatiu_id = bim_spatiu_id
    activity.zona_id = bim_zona_id
    activity.data = data_val
    activity.data_sfarsit = data_sfarsit_val
    activity.tip_activitate = tip_activitate
    activity.supervisor_id = supervisor_id if supervisor_id != angajat_id else None
    activity.subordonati_ids = subordonati_json
    activity.ore_lucrate = ore_lucrate_val
    activity.status_executie = status_executie
    activity.tip_instalatie_id = tip_instalatie_id
    activity.categorie_activitate_id = categorie_id
    activity.zona_lucru = zona_lucru
    activity.activitate_principala = activitate_principala[:500]
    activity.activitate_detaliata = activitate_detaliata[:2000] if activitate_detaliata else None
    activity.materiale_folosite = materiale_json
    activity.echipamente_folosite = echipamente or None
    activity.cantitate_executata = Decimal(cantitate) if cantitate else None
    activity.unitate_masura = um or None
    activity.procent_realizare = min(100, max(0, procent)) if procent is not None else None
    activity.probleme_intampinate = probleme or None
    activity.solutii_aplicate = solutii or None
    activity.observatii = observatii or None
    activity.necesita_aprobare_tehnica = necesita_aprobare
    activity.include_sambata = include_sambata
    activity.include_duminica = include_duminica
    activity.detalii_pe_zi = detalii_json

    # Auto-completare numar_saptamana / luna_an din tip si data inceput
    activity.calculeaza_perioada()

    if actiune == 'trimite':
        activity.status = 'trimis'
    elif activity.status == 'respins':
        activity.status = 'draft'

    db.session.commit()

    return {'activity': activity, 'actiune': actiune}


# ============================================================
# S1.1C — tranzitii de workflow (status)
# ============================================================

def submit_activity_for_approval(*, activity_id, tenant_id=None):
    """Tranzitie draft -> trimis pentru o activitate (tenant-safe).

    Mutat din routes/activitati.py::trimite. ID strain -> 404 (prin helper).
    Daca statusul nu este 'draft' nu muteaza nimic si nu face commit.

    Returneaza {'ok': bool, 'activity': <RaportActivitate>}: 'ok' True cand
    tranzitia a avut loc, False cand activitatea nu era in 'draft'.
    """
    activitate = get_activity_or_404(activity_id, tenant_id=tenant_id)
    if activitate.status != 'draft':
        return {'ok': False, 'activity': activitate}
    activitate.status = 'trimis'
    db.session.commit()
    return {'ok': True, 'activity': activitate}


def approve_activity(*, activity_id, approver_user, tenant_id=None):
    """Aproba o activitate (tenant-safe). Mutat din routes/activitati.py::aproba.

    Fara preconditie de status (comportament existent). Seteaza status, autorul
    aprobarii si data aprobarii. ID strain -> 404 inainte de mutatie.
    """
    activitate = get_activity_or_404(activity_id, tenant_id=tenant_id)
    activitate.status = 'aprobat'
    activitate.aprobat_de_id = approver_user.id
    activitate.data_aprobare = datetime.utcnow()
    db.session.commit()
    return {'ok': True, 'activity': activitate}


def reject_activity(*, activity_id, reason, tenant_id=None):
    """Respinge o activitate cu motiv (tenant-safe).

    Mutat din routes/activitati.py::respinge. `reason` este motivul deja citit
    din formular; daca este gol se aplica 'Fara motiv specificat' (identic cu
    comportamentul existent). ID strain -> 404 inainte de mutatie.
    """
    activitate = get_activity_or_404(activity_id, tenant_id=tenant_id)
    activitate.status = 'respins'
    activitate.motiv_respingere = reason or 'Fara motiv specificat'
    db.session.commit()
    return {'ok': True, 'activity': activitate}


def bulk_transition_activities(*, activity_ids, action, current_user,
                               rejection_reason=None, tenant_id=None):
    """Aprobare/respingere in masa (tenant-safe). Mutat din aprobare_masa.

    Pastreaza identic:
    - ramura off-mode legacy (RaportActivitate.query.get brut per id, skip silentios);
    - ramura tenant-aware: valideaza TOATE id-urile inainte de orice mutatie
      (abort 404 la id invalid/strain/lipsa), apoi pastreaza doar 'trimis';
    - orice actiune diferita de 'aproba' este tratata ca respingere (else),
      ca in codul existent;
    - un singur commit dupa bucla.

    Returneaza {'ok': True, 'count': int, 'action': str}.
    """
    if get_tenant_mode() == 'off':
        activitati = []
        for aid in activity_ids:
            try:
                a = RaportActivitate.query.get(int(aid))
                if a and a.status == 'trimis':
                    activitati.append(a)
            except (ValueError, TypeError):
                continue
    else:
        try:
            ids_int = [int(aid) for aid in activity_ids]
        except (ValueError, TypeError):
            ids_int = []
        ids_int = [aid for aid in ids_int if aid > 0]
        if len(ids_int) != len(activity_ids) or not ids_int:
            abort(404)
        activitati = query_activities_for_tenant(tenant_id=tenant_id).filter(
            RaportActivitate.id.in_(ids_int)
        ).all()
        if len({a.id for a in activitati}) != len(set(ids_int)):
            abort(404)
        activitati = [a for a in activitati if a.status == 'trimis']

    count = 0
    for a in activitati:
        if action == 'aproba':
            a.status = 'aprobat'
            a.aprobat_de_id = current_user.id
            a.data_aprobare = datetime.utcnow()
        else:
            a.status = 'respins'
            a.motiv_respingere = rejection_reason or 'Respins in masa'
        count += 1

    db.session.commit()

    return {'ok': True, 'count': count, 'action': action}


# ============================================================
# S1.1D — asamblare date pentru rapoarte/exporturi (tenant-safe)
# ============================================================
# Doar adunarea datelor tenant-safe; constructia workbook-ului/PDF-ului,
# template-urile si send_file raman in ruta (layout neschimbat).

def get_activity_rows_for_period(*, start_date, end_date, tenant_id=None):
    """Activitatile tenant-safe dintr-un interval [start_date, end_date].

    Ordonate identic cu rapoartele saptamanal/lunar/anual
    (angajat_id, apoi data). Returneaza o lista de RaportActivitate.
    """
    return query_activities_for_tenant(tenant_id=tenant_id).filter(
        RaportActivitate.data >= start_date,
        RaportActivitate.data <= end_date,
    ).order_by(RaportActivitate.angajat_id, RaportActivitate.data).all()


def get_timesheet_hours_map_for_period(*, start_date, end_date, tenant_id=None):
    """Map (angajat_id, data_iso) -> ore_lucrate pentru un interval, tenant-safe.

    Pastreaza fix-ul T1.C14: pontajele sunt citite prin query_timesheets_for_tenant(),
    niciodata prin Pontaj.query brut, ca sa nu scurga ore din alt tenant in raportul
    lunar. Returneaza un dict simplu, gata de folosit la randarea workbook-ului.
    """
    pontaje = query_timesheets_for_tenant(tenant_id=tenant_id).filter(
        Pontaj.data >= start_date, Pontaj.data <= end_date
    ).all()
    pontaj_map = {}
    for p in pontaje:
        pontaj_map[(p.angajat_id, p.data.isoformat())] = float(p.ore_lucrate) if p.ore_lucrate else 0
    return pontaj_map


def get_project_activity_report_data(*, project_id, tenant_id=None):
    """Proiectul validat tenant-safe + activitatile lui (pentru raportul pe proiect).

    Proiectul este obtinut prin get_project_or_404 (id strain -> 404). Activitatile
    sunt citite tenant-safe, ordonate descrescator dupa data (identic cu ruta).
    Returneaza {'proiect': <Proiect>, 'activitati': [<RaportActivitate>, ...]}.
    """
    proiect = get_project_or_404(project_id, tenant_id=tenant_id)
    activitati = query_activities_for_tenant(tenant_id=tenant_id).filter_by(
        proiect_id=project_id
    ).order_by(RaportActivitate.data.desc()).all()
    return {'proiect': proiect, 'activitati': activitati}
