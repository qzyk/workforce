"""
Punte Gantt -> BIM 4D.

Dintr-un plan Gantt (RezultatPlanificare), genereaza/actualizeaza intrari
`bim_task_schedules` pentru elementele unui model/santier: fiecare element
mosteneste fereastra de date a categoriei lui tehnologice (mapata din tip_element
prin store.mapare_tip_element). Apoi viewer-ul coloreaza obiectele dupa stare la
o data data (4D).
"""
from __future__ import annotations

from datetime import date

from services.gantt import store
from services.gantt.diagrama import _calendar_lucrator


def ferestre_categorii(rezultat, data_start: date) -> dict:
    """{CATEGORIE: (data_start, data_sfarsit)} - fereastra min/max a activitatilor."""
    durata = int((rezultat.statistici or {}).get('durata_totala_zile', 0) or 0)
    cal = _calendar_lucrator(data_start, durata)

    def dz(i: int) -> date:
        return cal[max(0, min(int(i), len(cal) - 1))]

    indici: dict = {}
    for a in (rezultat.activitati or []):
        cat = a.categorie_tehnologica
        if not cat:
            continue
        s, f = indici.get(cat, (10 ** 9, -1))
        indici[cat] = (min(s, a.start_zi), max(f, a.finish_zi))
    return {cat: (dz(s), dz(max(f - 1, s))) for cat, (s, f) in indici.items()}


def genereaza_din_rezultat(elemente, rezultat, data_start: date, mapare: dict,
                           tenant_id=None, user_id=None) -> dict:
    """Upsert bim_task_schedules pentru `elemente` din fereastra categoriei mapate.
    Intoarce {create, actualizate, sarite, categorii}."""
    from models import db, BIMTaskSchedule
    ferestre = ferestre_categorii(rezultat, data_start)
    crt = act = sarit = 0
    for el in elemente:
        cat = mapare.get(el.tip_element)
        if not cat or cat not in ferestre:
            sarit += 1
            continue
        ds, de = ferestre[cat]
        faza = cat.lower()
        sched = BIMTaskSchedule.query.filter_by(element_bim_id=el.id, faza=faza).first()
        if sched:
            sched.data_start_plan = ds
            sched.data_sfarsit_plan = de
            act += 1
        else:
            db.session.add(BIMTaskSchedule(
                element_bim_id=el.id, faza=faza, data_start_plan=ds,
                data_sfarsit_plan=de, status='planificat', progres_pct=0,
                tenant_id=tenant_id, creat_de_id=user_id))
            crt += 1
    db.session.commit()
    try:
        from services import audit
        audit.log('update', 'bim_task_schedule', None,
                  new_values={'din_plan_gantt': True, 'create': crt, 'actualizate': act},
                  commit=True)
    except Exception:
        pass
    return {'create': crt, 'actualizate': act, 'sarite': sarit,
            'categorii': len(ferestre)}


def stare_la_data(data_start_plan: date, data_sfarsit_plan: date, d: date) -> str:
    """'neinceput' | 'in_curs' | 'finalizat' la data d."""
    if d < data_start_plan:
        return 'neinceput'
    if d > data_sfarsit_plan:
        return 'finalizat'
    return 'in_curs'


def date_4d(perechi, data_curenta: date = None) -> dict:
    """Date pentru player-ul din viewer. `perechi` = iterable de (element, schedule).
    Intoarce {data_min, data_max, nr, elemente:[{guid, start, finish, faza, stare}]}."""
    elemente = []
    dmin = dmax = None
    for el, sched in perechi:
        if not el.ifc_global_id:
            continue
        ds, de = sched.data_start_plan, sched.data_sfarsit_plan
        dmin = ds if dmin is None or ds < dmin else dmin
        dmax = de if dmax is None or de > dmax else dmax
        elemente.append({
            'guid': el.ifc_global_id, 'start': ds.isoformat(), 'finish': de.isoformat(),
            'faza': sched.faza, 'tip': el.tip_element,
            'stare': (stare_la_data(ds, de, data_curenta) if data_curenta else 'neinceput'),
        })
    return {
        'data_min': dmin.isoformat() if dmin else None,
        'data_max': dmax.isoformat() if dmax else None,
        'nr': len(elemente), 'elemente': elemente,
    }
