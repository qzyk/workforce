"""
Earned Value Management (EVM) la nivel de proiect.

Compara PLANIFICAT (curba S din planul Gantt) cu REALIZAT (situatiile lunare):
  PV (Planned Value)  = % planificat la data X  x  BAC
  EV (Earned Value)   = % avans real (situatie) x  BAC
  AC (Actual Cost)    = valoare cumulata real (situatie)
  SPI = EV / PV  (>1 = inaintea graficului)
  CPI = EV / AC  (>1 = sub buget)

BAC (Budget At Completion) = costul total estimat din planul Gantt.
"""
from __future__ import annotations

from datetime import date


def _pv_calendar(plan):
    """([(date, procent_planificat)], BAC) din curba S a planului Gantt."""
    import json
    from services.gantt.pipeline import MotorPlanificare
    from services.gantt import import_engine
    from services.gantt.diagrama import _calendar_lucrator

    mapare = rand_antet = None
    if plan.mapare_json:
        try:
            d = json.loads(plan.mapare_json)
            mapare, rand_antet = d.get('coloane'), d.get('rand_antet')
        except Exception:
            pass
    # 5D real: daca proiectul are oferta pretuita, costam pe preturile din deviz
    preturi = None
    if getattr(plan, 'proiect_id', None):
        try:
            from services.deviz_link import preturi_proiect, are_preturi
            pb = preturi_proiect(plan.proiect_id)
            preturi = pb if are_preturi(pb) else None
        except Exception:
            preturi = None
    motor = MotorPlanificare(preturi_boq=preturi)
    art, _ = import_engine.importa(plan.continut, plan.ext, motor.setari,
                                   mapare_manuala=mapare, rand_antet_manual=rand_antet)
    st = motor.proceseaza(art).statistici
    durata = int(st.get('durata_totala_zile', 0) or 0)
    cal = _calendar_lucrator(plan.data_start or date.today(), durata)

    def dz(i):
        return cal[max(0, min(int(i), len(cal) - 1))]

    pts = [(dz(p['zi'] - 1), float(p['procent'])) for p in st.get('curba_s', [])]
    # BAC: costul recalculat (cu preturi reale daca exista), altfel snapshot-ul planului
    bac = float(st.get('cost_total', 0) or plan.cost_total or 0)
    return pts, bac


def _pv_la_data(pv_pts, d: date) -> float:
    """Procentul planificat la data d (functie-treapta: ultimul punct <= d)."""
    if not pv_pts:
        return 0.0
    proc = 0.0
    for dt, p in pv_pts:
        if dt <= d:
            proc = p
        else:
            break
    if d >= pv_pts[-1][0]:
        proc = pv_pts[-1][1]
    return proc


def evm_proiect(proiect_id: int, tenant_id=None) -> dict:
    """EVM pentru un proiect (None daca nu exista plan Gantt). Robust la date lipsa."""
    from models import GanttPlan, SituatieLunara
    plan = (GanttPlan.query.filter_by(proiect_id=proiect_id)
            .order_by(GanttPlan.data_creare.desc()).first())
    if not plan:
        return None
    try:
        pv_pts, bac = _pv_calendar(plan)
    except Exception:
        pv_pts, bac = [], float(plan.cost_total or 0)

    situatii = (SituatieLunara.query.filter_by(proiect_id=proiect_id)
                .order_by(SituatieLunara.an, SituatieLunara.luna).all())
    serie = []
    for s in situatii:
        d = s.data_emitere or date(int(s.an or date.today().year), int(s.luna or 1),
                                   min(28, 28))
        ev_pct = float(s.procent_avans_total or 0)
        ac = float(s.valoare_cumulat_la_zi or 0)
        pv_pct = _pv_la_data(pv_pts, d)
        ev_val = ev_pct / 100.0 * bac
        serie.append({
            'data': d.isoformat(), 'pv_pct': round(pv_pct, 1), 'ev_pct': round(ev_pct, 1),
            'pv_val': round(pv_pct / 100.0 * bac, 0), 'ev_val': round(ev_val, 0),
            'ac': round(ac, 0),
            'spi': round(ev_pct / pv_pct, 2) if pv_pct else None,
            'cpi': round(ev_val / ac, 2) if ac else None,
        })
    return {
        'bac': round(bac, 0), 'plan_nume': plan.nume, 'nr_situatii': len(situatii),
        'serie': serie, 'ultim': (serie[-1] if serie else None),
        'pv_curba': [{'data': dt.isoformat(), 'procent': round(p, 1)} for dt, p in pv_pts],
    }
