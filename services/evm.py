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

# tarif orar implicit (lei/ora) cand angajatul nu are tarif_negociat pe proiect
TARIF_ORAR_IMPLICIT = 30.0


def _pontaje_cumulativ(proiect_id: int):
    """([(data, cost_cumulat)], total_ore) din pontaje (cost manopera reala).
    cost = ore_lucrate x tarif + prime ore suplimentare; tarif din AngajatProiect."""
    from models import Pontaj, AngajatProiect
    tarife = {ap.angajat_id: float(ap.tarif_negociat or 0)
              for ap in AngajatProiect.query.filter_by(proiect_id=proiect_id).all()}
    pontaje = (Pontaj.query.filter_by(proiect_id=proiect_id)
               .order_by(Pontaj.data).all())
    cum, ore_tot, serie = 0.0, 0.0, []
    for p in pontaje:
        t = tarife.get(p.angajat_id) or TARIF_ORAR_IMPLICIT
        base = float(p.ore_lucrate or 0)
        h50 = float(p.ore_suplimentare_50 or 0)
        h100 = float(p.ore_suplimentare_100 or 0)
        cum += t * base + t * 0.5 * h50 + t * 1.0 * h100
        ore_tot += base
        serie.append((p.data, round(cum, 2)))
    return serie, round(ore_tot, 1)


def _man_la_data(serie, d: date) -> float:
    """Cost manopera cumulat la data d (functie-treapta)."""
    val = 0.0
    for dt, c in serie:
        if dt and dt <= d:
            val = c
        else:
            break
    return val


def _utilaj_cumulativ(proiect_id: int):
    """([(data, cost_cumulat)], total_ore) din ConsumUtilaj (cost utilaj real)."""
    from models import ConsumUtilaj
    randuri = (ConsumUtilaj.query.filter_by(proiect_id=proiect_id)
               .order_by(ConsumUtilaj.data).all())
    cum, ore_tot, serie = 0.0, 0.0, []
    for r in randuri:
        cum += r.calc_cost()
        ore_tot += float(r.ore or 0)
        serie.append((r.data, round(cum, 2)))
    return serie, round(ore_tot, 1)


def _pv_calendar(plan):
    """([(date, procent_planificat)], BAC, utilaj_planificat) din curba S a planului."""
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
    utilaj_plan = float(st.get('cost_utilaj', 0) or 0)   # utilaj planificat (Faza 3)
    return pts, bac, utilaj_plan


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


def risc_proiect(proiect_id: int) -> dict:
    """Evaluare RAPIDA de risc (fara re-rularea pipeline-ului): SPI/CPI din ultima
    situatie vs plan (PV liniar din durata). {spi, cpi, status, ev_pct} sau None."""
    from models import GanttPlan, SituatieLunara
    plan = (GanttPlan.query.filter_by(proiect_id=proiect_id)
            .order_by(GanttPlan.data_creare.desc()).first())
    sit = (SituatieLunara.query.filter_by(proiect_id=proiect_id)
           .order_by(SituatieLunara.id.desc()).first())
    if not plan or not sit:
        return None
    bac = float(plan.cost_total or 0)
    ev_pct = float(sit.procent_avans_total or 0)
    ac = float(sit.valoare_cumulat_la_zi or 0)
    d = sit.data_emitere or date(int(sit.an or date.today().year), int(sit.luna or 1), 28)
    durata = int(plan.durata_zile or 0)
    pv_pct = 0.0
    if plan.data_start and durata > 0:
        pv_pct = max(0.0, min(100.0, (d - plan.data_start).days / durata * 100.0))
    spi = round(ev_pct / pv_pct, 2) if pv_pct else None
    cpi = round((ev_pct / 100.0 * bac) / ac, 2) if ac else None
    status = 'ok'
    if (cpi is not None and cpi < 0.9) or (spi is not None and spi < 0.9):
        status = 'critic'
    elif (cpi is not None and cpi < 1.0) or (spi is not None and spi < 1.0):
        status = 'atentie'
    return {'spi': spi, 'cpi': cpi, 'status': status, 'ev_pct': round(ev_pct, 1)}


def evm_proiect(proiect_id: int, tenant_id=None) -> dict:
    """EVM pentru un proiect (None daca nu exista plan Gantt). Robust la date lipsa."""
    from models import GanttPlan, SituatieLunara
    plan = (GanttPlan.query.filter_by(proiect_id=proiect_id)
            .order_by(GanttPlan.data_creare.desc()).first())
    if not plan:
        return None
    try:
        pv_pts, bac, utilaj_plan = _pv_calendar(plan)
    except Exception:
        pv_pts, bac, utilaj_plan = [], float(plan.cost_total or 0), 0.0

    pont_serie, pont_ore = _pontaje_cumulativ(proiect_id)   # manopera reala (pontaje)
    man_total = pont_serie[-1][1] if pont_serie else 0.0
    util_serie, util_ore = _utilaj_cumulativ(proiect_id)    # utilaj real (ConsumUtilaj)
    util_total = util_serie[-1][1] if util_serie else 0.0
    # B: utilaj PLANIFICAT din extrasul C8 (daca importat), altfel estimarea din plan
    util_plan_ore, util_sursa = 0.0, 'plan'
    try:
        from models import ExtrasResursa
        c8 = ExtrasResursa.query.filter_by(proiect_id=proiect_id, tip='utilaj').all()
        if c8:
            utilaj_plan = sum(float(x.valoare or 0) for x in c8)
            util_plan_ore = sum(float(x.cantitate or 0) for x in c8)
            util_sursa = 'C8'
    except Exception:
        pass

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
            'ac': round(ac, 0), 'man_pontat': round(_man_la_data(pont_serie, d), 0),
            'utilaj_real': round(_man_la_data(util_serie, d), 0),
            'spi': round(ev_pct / pv_pct, 2) if pv_pct else None,
            'cpi': round(ev_val / ac, 2) if ac else None,
        })
    return {
        'bac': round(bac, 0), 'plan_nume': plan.nume, 'nr_situatii': len(situatii),
        'manopera': {'cost': round(man_total, 0), 'ore': pont_ore},
        'utilaj': {'planificat': round(utilaj_plan, 0), 'real': round(util_total, 0),
                   'ore': util_ore, 'planificat_ore': round(util_plan_ore, 1),
                   'sursa': util_sursa},
        'serie': serie, 'ultim': (serie[-1] if serie else None),
        'pv_curba': [{'data': dt.isoformat(), 'procent': round(p, 1)} for dt, p in pv_pts],
    }
