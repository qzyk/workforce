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
from datetime import datetime, date, timedelta

from models import (
    Angajat, Proiect, TipInstalatie, CategorieActivitate,
    RaportActivitate, Santier, Cladire, ElementBIM, SarbatoareLegala,
)
from services.security.tenant_access import (
    query_activities_for_tenant,
    query_bim_buildings_for_tenant,
    query_bim_elements_for_tenant,
    query_sites_for_tenant,
    query_for_tenant,
)


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
