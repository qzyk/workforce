"""
Baseline EVM materializat (PMB - Performance Measurement Baseline).

De ce: azi PV (Planned Value) se recalculeaza LIVE la fiecare cerere EVM, prin
re-rularea pipeline-ului Gantt (import + procesare F3). E fragil (erori inghitite
tacut) si lent (acelasi plan reprocesat de mai multe ori pe aceeasi pagina).
Solutia: la aprobarea programului, INGHETAM curba PV + BAC intr-un snapshot
(`EvmBaseline.continut_json`) si masuram fata de el. Referinta contractuala
ramane stabila chiar daca planul/preturile se schimba ulterior.

Acest modul e adaptorul DB (separat de evm.py, care ramane pur calcul). Respecta
feature flag-ul 'evm-baseline':
  - flag OFF -> `get_baseline_activ` intoarce None -> evm_proiect recalculeaza live
    (comportament istoric, zero regresie);
  - flag ON  -> evm_proiect foloseste PV/BAC din baseline-ul activ daca exista,
    altfel cade tot pe recalcul live (un proiect fara snapshot nu se schimba).

Snapshot-ul foloseste exact aceeasi sursa ca recalculul live (`evm._pv_calendar`),
deci PV-ul inghetat nu poate diverge de cel calculat in momentul inghetarii.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional


def _flag_on(tenant_id: Optional[int] = None) -> bool:
    """True doar cand flag-ul 'evm-baseline' e activ (altfel istoric, recalcul live)."""
    try:
        from services.feature_flags import is_enabled
        return bool(is_enabled('evm-baseline', tenant_id))
    except Exception:
        return False


def _bac_contract(proiect_id: int) -> Optional[float]:
    """Valoarea contractuala (Contract activ principal) a proiectului, daca exista.

    Folosita DOAR pentru validare/avertizare: BAC-ul EVM vine din costul planului
    Gantt si poate diverge legitim de valoarea de contract (preturi de cost vs
    pret de vanzare, acte aditionale neaplicate inca). Nu suprascriem BAC-ul -
    doar semnalam divergenta in meta-ul snapshot-ului."""
    try:
        from models import Contract
        c = (Contract.query
             .filter_by(proiect_id=proiect_id, parinte_contract_id=None)
             .order_by(Contract.id.desc()).first())
        if c is not None and c.valoare_totala is not None:
            return float(c.valoare_totala)
    except Exception:
        pass
    return None


def snapshot_baseline(proiect, nume: str = None, tenant_id: Optional[int] = None,
                      creat_de_id: int = None):
    """Ingheata baseline-ul EVM curent al unui proiect (PV + BAC din planul Gantt).

    Creeaza un `EvmBaseline` activ si il marcheaza ca baseline activ pe proiect
    (`proiect.baseline_evm_activ_id`), dezactivand baseline-urile anterioare
    (pastram istoricul randurilor, doar `activ=False`).

    `proiect` poate fi instanta Proiect sau id (int). Intoarce randul EvmBaseline
    sau None daca proiectul nu are plan Gantt din care sa derivam curba.

    Nu cere flag ON: inghetarea e o actiune explicita (endpoint), iar flag-ul
    controleaza doar CITIREA (get_baseline_activ / evm_proiect).
    """
    from models import db, Proiect, GanttPlan
    from services.evm import _pv_calendar

    proiect_id = proiect if isinstance(proiect, int) else proiect.id
    p = proiect if not isinstance(proiect, int) else db.session.get(Proiect, proiect_id)
    if p is None:
        return None

    plan = (GanttPlan.query.filter_by(proiect_id=proiect_id)
            .order_by(GanttPlan.data_creare.desc()).first())
    if plan is None:
        return None

    # Aceeasi sursa ca recalculul live -> PV inghetat == PV calculat la inghetare.
    try:
        pv_pts, bac, utilaj_plan = _pv_calendar(plan)
    except Exception:
        # Plan necitibil: nu inghetam un baseline gol (ar masca eroarea). Mai bine None.
        return None

    bac = float(bac or 0)
    bac_contract = _bac_contract(proiect_id)
    # Divergenta BAC plan vs valoarea de contract (informativ; nu blocheaza).
    divergenta_contract = None
    if bac_contract:
        divergenta_contract = round((bac - bac_contract) / bac_contract * 100.0, 1)

    snap = {
        'pv_curba': [{'data': dt.isoformat(), 'procent': round(pr, 1)}
                     for dt, pr in pv_pts],
        'meta': {
            'bac': round(bac, 2),
            'plan_id': plan.id,
            'plan_nume': plan.nume,
            'utilaj_planificat': round(float(utilaj_plan or 0), 2),
            'data_start': plan.data_start.isoformat() if plan.data_start else None,
            'durata_zile': int(plan.durata_zile or 0),
            'bac_contract': round(bac_contract, 2) if bac_contract is not None else None,
            'divergenta_contract_pct': divergenta_contract,
        },
    }

    nume = (nume or f'Baseline EVM {datetime.utcnow().strftime("%Y-%m-%d %H:%M")}')[:120]

    # Dezactiveaza baseline-urile anterioare (pastram istoricul, doar activ=False).
    from models import EvmBaseline
    (EvmBaseline.query.filter_by(proiect_id=proiect_id, activ=True)
     .update({'activ': False}, synchronize_session=False))

    bl = EvmBaseline(
        tenant_id=tenant_id, proiect_id=proiect_id, nume=nume,
        bac=round(bac, 2), continut_json=json.dumps(snap),
        activ=True, creat_de_id=creat_de_id)
    db.session.add(bl)
    db.session.flush()             # avem nevoie de bl.id pentru baseline_evm_activ_id
    p.baseline_evm_activ_id = bl.id
    db.session.commit()
    return bl


def get_baseline_activ(proiect, tenant_id: Optional[int] = None) -> Optional[dict]:
    """Snapshot-ul baseline-ului EVM activ (dict desfacut din JSON), DOAR cu flag ON.

    Intoarce None cand: flag OFF (-> recalcul live, istoric), proiectul nu are
    baseline activ, sau snapshot-ul e gol/corupt. `proiect` poate fi instanta sau id.
    """
    if not _flag_on(tenant_id):
        return None
    from models import db, Proiect, EvmBaseline
    proiect_id = proiect if isinstance(proiect, int) else proiect.id
    p = proiect if not isinstance(proiect, int) else db.session.get(Proiect, proiect_id)
    if p is None:
        return None
    bid = getattr(p, 'baseline_evm_activ_id', None)
    bl = None
    if bid:
        bl = db.session.get(EvmBaseline, bid)
    if bl is None:
        # fallback: cel mai recent baseline activ pe proiect (robust la pointer lipsa)
        bl = (EvmBaseline.query.filter_by(proiect_id=proiect_id, activ=True)
              .order_by(EvmBaseline.id.desc()).first())
    if bl is None or not bl.continut_json:
        return None
    try:
        return json.loads(bl.continut_json)
    except Exception:
        return None
