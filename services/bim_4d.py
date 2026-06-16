"""
4D Schedule service: link elemente BIM la task-uri planificate.

Capabilitati:
- create/update schedule entry
- query: ce elemente sunt vizibile la o anumita data (construction sequencing)
- progress autocompute: pe baza zilelor scurse + status
- comparativ: planificat vs real (intarziere)
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from models import db, BIMTaskSchedule, ElementBIM, Cladire
from services import audit as audit_svc


_logger = logging.getLogger(__name__)


# ====================================================
# CRUD
# ====================================================

def create_schedule(element_bim_id: int, faza: str,
                    data_start_plan: date, data_sfarsit_plan: date,
                    *, user, disciplina: Optional[str] = None,
                    descriere: Optional[str] = None,
                    raport_activitate_id: Optional[int] = None,
                    tenant_id: Optional[int] = None,
                    commit: bool = True) -> BIMTaskSchedule:
    """Creeaza un task schedule pentru un element."""
    if data_start_plan > data_sfarsit_plan:
        raise ValueError('data_start_plan trebuie <= data_sfarsit_plan')

    sched = BIMTaskSchedule(
        tenant_id=tenant_id,
        element_bim_id=element_bim_id,
        faza=faza.strip().lower() if faza else 'altele',
        disciplina=disciplina.upper() if disciplina else None,
        descriere=(descriere or '').strip() or None,
        data_start_plan=data_start_plan,
        data_sfarsit_plan=data_sfarsit_plan,
        progres_pct=0,
        status='planificat',
        raport_activitate_id=raport_activitate_id,
        creat_de_id=getattr(user, 'id', None) if user else None,
    )
    db.session.add(sched)
    db.session.flush()

    audit_svc.log_create('bim_task_schedule', sched.id, new_values={
        'element_bim_id': element_bim_id,
        'faza': sched.faza,
        'data_start_plan': data_start_plan.isoformat(),
        'data_sfarsit_plan': data_sfarsit_plan.isoformat(),
    })

    if commit:
        db.session.commit()
    return sched


def update_progress(schedule: BIMTaskSchedule, progres_pct: int, *,
                    status: Optional[str] = None,
                    user=None, commit: bool = True) -> BIMTaskSchedule:
    """Actualizeaza progresul unui schedule + auto-status."""
    progres_pct = max(0, min(100, int(progres_pct)))
    old_progres = schedule.progres_pct
    old_status = schedule.status
    schedule.progres_pct = progres_pct

    # Auto-update status pe baza progresului (daca user-ul nu specifica)
    if status:
        schedule.status = status
    else:
        if progres_pct == 0:
            schedule.status = 'planificat'
        elif progres_pct == 100:
            schedule.status = 'finalizat'
            if not schedule.data_sfarsit_real:
                schedule.data_sfarsit_real = date.today()
        else:
            schedule.status = 'in_curs'
            if not schedule.data_start_real:
                schedule.data_start_real = date.today()

    if old_progres != progres_pct or old_status != schedule.status:
        audit_svc.log_update(
            'bim_task_schedule', schedule.id,
            old_values={'progres_pct': old_progres, 'status': old_status},
            new_values={'progres_pct': progres_pct, 'status': schedule.status},
        )

    if commit:
        db.session.commit()
    return schedule


# ====================================================
# SYNC plan <-> actuals (4D)
# Propaga progresul real raportat din executie (RaportActivitate) catre
# schedule-urile 4D legate de acelasi element BIM. Reutilizeaza update_progress.
# ====================================================

def _flag_4d_enabled() -> bool:
    """True cand flag-ul '4D schedule' e activ (per tenant sau global)."""
    try:
        from services import feature_flags as ff
        return ff.is_enabled('bim-4d-schedule')
    except Exception:
        return False


def _progres_real_pe_element() -> dict:
    """
    {element_bim_id: procent_max} agregat din RaportActivitate.

    Un element poate avea mai multe rapoarte (zile/echipe diferite). Luam
    MAXIMUL procent_realizare: elementul e cel putin atat de avansat cat
    indica cel mai avansat raport. Ignoram rapoartele fara procent_realizare
    (nu suprascriem un progres existent cu 0 implicit)."""
    from models import RaportActivitate
    agregat: dict[int, int] = {}
    rapoarte = (RaportActivitate.query
                .filter(RaportActivitate.element_bim_id.isnot(None),
                        RaportActivitate.procent_realizare.isnot(None))
                .all())
    for r in rapoarte:
        pct = max(0, min(100, int(r.procent_realizare)))
        eid = r.element_bim_id
        if pct > agregat.get(eid, -1):
            agregat[eid] = pct
    return agregat


def sync_actuals_pentru_element(element_bim_id: int, *, user=None,
                                commit: bool = True) -> dict:
    """
    Sincronizeaza progresul real al unui singur element catre toate schedule-urile lui.

    Sursa: MAXIMUL RaportActivitate.procent_realizare pe acel element.
    Tinta: BIMTaskSchedule.progres_pct (via update_progress, care auto-deriva status).

    Idempotent: re-rularea cu aceleasi date nu produce schimbari (update_progress
    actualizeaza doar la diferenta). Returneaza {actualizate, fara_schimbare, progres}."""
    from models import RaportActivitate

    rezultat = {'actualizate': 0, 'fara_schimbare': 0, 'progres': None}
    if not _flag_4d_enabled():
        return rezultat

    pct_row = (db.session.query(db.func.max(RaportActivitate.procent_realizare))
               .filter(RaportActivitate.element_bim_id == element_bim_id,
                       RaportActivitate.procent_realizare.isnot(None))
               .scalar())
    if pct_row is None:
        return rezultat  # niciun raport cu procent -> nimic de sincronizat
    progres = max(0, min(100, int(pct_row)))
    rezultat['progres'] = progres

    schedules = BIMTaskSchedule.query.filter_by(element_bim_id=element_bim_id).all()
    for sched in schedules:
        if sched.progres_pct == progres:
            rezultat['fara_schimbare'] += 1
            continue
        update_progress(sched, progres, user=user, commit=False)
        rezultat['actualizate'] += 1

    if commit and rezultat['actualizate']:
        db.session.commit()
    return rezultat


def sync_actuals_din_rapoarte(*, santier_id: Optional[int] = None,
                              user=None, commit: bool = True) -> dict:
    """
    Sincronizeaza in masa progresul real (RaportActivitate.procent_realizare) catre
    schedule-urile 4D, prin element_bim_id comun. Gate pe flag 'bim-4d-schedule'.

    Daca santier_id e dat, se limiteaza la elementele acelui santier; altfel global.
    Idempotent. Returneaza {elemente, actualizate, fara_schimbare, sarite}.

    Acoperire (de ce e MAJOR in audit): pana acum progres_pct era manual si
    decuplat de executia reala. Aceasta punte inchide bucla plan<->actuals 4D."""
    rezultat = {'elemente': 0, 'actualizate': 0, 'fara_schimbare': 0, 'sarite': 0}
    if not _flag_4d_enabled():
        return rezultat

    agregat = _progres_real_pe_element()
    if not agregat:
        return rezultat

    # Restrangere optionala la elementele unui santier
    elemente_permise = None
    if santier_id is not None:
        cladiri_ids = [c.id for c in Cladire.query.filter_by(santier_id=santier_id).all()]
        if not cladiri_ids:
            return rezultat
        elemente_permise = {
            e.id for e in ElementBIM.query
            .filter(ElementBIM.cladire_id.in_(cladiri_ids)).all()
        }

    for element_bim_id, progres in agregat.items():
        if elemente_permise is not None and element_bim_id not in elemente_permise:
            continue
        schedules = BIMTaskSchedule.query.filter_by(
            element_bim_id=element_bim_id).all()
        if not schedules:
            rezultat['sarite'] += 1
            continue
        rezultat['elemente'] += 1
        for sched in schedules:
            if sched.progres_pct == progres:
                rezultat['fara_schimbare'] += 1
                continue
            update_progress(sched, progres, user=user, commit=False)
            rezultat['actualizate'] += 1

    if commit and rezultat['actualizate']:
        db.session.commit()
    try:
        from services import audit
        audit.log('sync_actuals', 'bim_task_schedule', None,
                  new_values={'santier_id': santier_id,
                              'elemente': rezultat['elemente'],
                              'actualizate': rezultat['actualizate']},
                  commit=True)
    except Exception:
        pass
    return rezultat


# ====================================================
# QUERY: 4D Timeline
# ====================================================

def get_timeline_for_santier(santier_id: int) -> list[BIMTaskSchedule]:
    """Toate schedule entries pentru elementele unui santier, sortate dupa data start."""
    cladiri_ids = [c.id for c in Cladire.query.filter_by(santier_id=santier_id).all()]
    if not cladiri_ids:
        return []
    return (BIMTaskSchedule.query
            .join(ElementBIM, ElementBIM.id == BIMTaskSchedule.element_bim_id)
            .filter(ElementBIM.cladire_id.in_(cladiri_ids))
            .order_by(BIMTaskSchedule.data_start_plan,
                      BIMTaskSchedule.data_sfarsit_plan)
            .all())


def get_visible_elements_at_date(santier_id: int, data: date) -> list[int]:
    """
    Returneaza ID-urile elementelor BIM care sunt deja construite (cel putin partial)
    la data data. Folosit pentru construction sequencing in 3D viewer.
    """
    cladiri_ids = [c.id for c in Cladire.query.filter_by(santier_id=santier_id).all()]
    if not cladiri_ids:
        return []
    # Selectam elementele cu schedule unde data_start_plan <= data
    schedules = (BIMTaskSchedule.query
                 .join(ElementBIM, ElementBIM.id == BIMTaskSchedule.element_bim_id)
                 .filter(ElementBIM.cladire_id.in_(cladiri_ids),
                         BIMTaskSchedule.data_start_plan <= data)
                 .all())
    return list({s.element_bim_id for s in schedules})


def compute_santier_progress(santier_id: int) -> dict:
    """
    Calculeaza progresul global al unui santier:
    - total tasks
    - tasks finalizate
    - progres mediu ponderat (pe durata)
    - elemente intarziate
    """
    timeline = get_timeline_for_santier(santier_id)
    if not timeline:
        return {'total_tasks': 0, 'finalizate': 0, 'progres_mediu': 0,
                'intarziate': 0, 'in_curs': 0}

    finalizate = sum(1 for t in timeline if t.status == 'finalizat')
    in_curs = sum(1 for t in timeline if t.status == 'in_curs')
    intarziate = sum(1 for t in timeline if t.este_intarziat)

    # Progres mediu ponderat pe durata
    total_durata = sum(t.durata_zile_plan for t in timeline)
    if total_durata > 0:
        progres_ponderat = sum(
            t.progres_pct * t.durata_zile_plan for t in timeline
        ) / total_durata
    else:
        progres_ponderat = sum(t.progres_pct for t in timeline) / len(timeline)

    return {
        'total_tasks': len(timeline),
        'finalizate': finalizate,
        'in_curs': in_curs,
        'intarziate': intarziate,
        'progres_mediu': round(progres_ponderat, 1),
    }
