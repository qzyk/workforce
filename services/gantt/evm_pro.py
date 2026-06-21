"""
EVM (Earned Value Management) la nivel de PLAN Gantt, din datele de tracking.

Diferenta fata de services/evm.py (care lucreaza la nivel de PROIECT, cu EV/AC din
situatii lunare): aici masuram performanta unui PLAN Gantt salvat folosind stratul
de urmarire din Gantt Faza 2:
  PV (Planned Value) = curba S a BASELINE-ului activ (GanttBaseline.continut_json),
                       mapata pe date reale; nu din planul "viu" (care deriva la
                       editari de tarife/randamente). Referinta stabila.
  EV (Earned Value)  = sum( procent_fizic(activitate) / 100 x valoare(activitate) ),
                       agregat la DATA DE STARE din jurnalul GanttProgres (ultima
                       masuratoare <= data de stare, pe cheia stabila). Valorile de
                       activitate vin din snapshot-ul baseline-ului (inghetate).
  AC (Actual Cost)   = cost real cumulat la data de stare: manopera pontata +
                       utilaj real (ConsumUtilaj). Fallback documentat: daca nu
                       exista pontaje/consum, cade pe valoarea cumulata din ultima
                       SituatieLunara <= data de stare. None-safe cand lipseste tot.
  SPI = EV/PV, CPI = EV/AC; forecast (EAC/ETC/VAC/TCPI) = services.evm._prognoza.

NU duplicam formulele: _prognoza (forecast) si _pontaje_cumulativ/_utilaj_cumulativ/
_man_la_data/_pv_la_data sunt REUTILIZATE din services.evm.

Activare: DOAR cu flag-ul 'gantt-evm-pro' ON *si* baseline activ pe plan. In rest
(flag OFF, plan fara baseline, plan fara progres) -> None (comportament neschimbat:
fara EVM pe plan). Rezultatul e CACHE-uit pe instanta de plan, pe (id, data de stare),
ca sa nu re-rulam agregarea de mai multe ori pe acelasi request.
"""
from __future__ import annotations

from datetime import date
from typing import Optional


def _flag_on(tenant_id: Optional[int] = None) -> bool:
    """True doar cand flag-ul 'gantt-evm-pro' e activ (altfel fara EVM pe plan)."""
    try:
        from services.feature_flags import is_enabled
        return bool(is_enabled('gantt-evm-pro', tenant_id))
    except Exception:
        return False


def _pv_din_baseline_gantt(snap: dict, data_start: date, calendar=None):
    """([(date, procent)], BAC, data_start) din snapshot-ul de baseline Gantt.

    Snapshot-ul Gantt (tracking.snapshot_baseline) tine curba S ca [{zi, procent}]
    (indecsi 1-based), spre deosebire de baseline-ul EVM (pv_curba cu date). Mapam
    zi->data ca in evm._pv_calendar, folosind data de start a baseline-ului si
    calendarul de lucru (None = doar Lu-Vi, istoric).
    """
    from services.gantt.diagrama import _calendar_lucrator
    curba = (snap or {}).get('curba_s') or []
    meta = (snap or {}).get('meta') or {}
    bac = float(meta.get('bac') or 0)
    durata = int(meta.get('durata_zile') or 0)
    if not curba or durata <= 0:
        return [], bac, data_start
    cal = _calendar_lucrator(data_start or date.today(), durata, calendar)

    def dz(i):
        return cal[max(0, min(int(i), len(cal) - 1))]

    pts = [(dz(int(p.get('zi', 1)) - 1), float(p.get('procent', 0) or 0)) for p in curba]
    return pts, bac, data_start


def _valori_din_baseline(snap: dict) -> dict:
    """{cheie_activitate: valoare} din snapshot-ul de baseline (valori inghetate).

    EV se pondereaza pe aceste valori (referinta contractuala), nu pe valorile
    planului curent (care pot fi deviat de re-pretuire dupa inghetarea baseline-ului).
    """
    acts = (snap or {}).get('activitati') or {}
    out: dict = {}
    for ck, a in acts.items():
        try:
            out[ck] = float((a or {}).get('valoare') or 0)
        except (TypeError, ValueError):
            out[ck] = 0.0
    return out


def _ev_la_data(plan_id: int, valori: dict, data_stare: date) -> dict:
    """EV agregat la data de stare din jurnalul GanttProgres (append-only).

    Pentru fiecare cheie de activitate, ia ultima masuratoare cu data <= data_stare
    (ordonat dupa data, apoi data_creare) si pondereaza procentul pe valoarea
    inghetata a activitatii. Intoarce {ev, ev_pct, nr_cu_progres, val_total}.
    """
    from models import GanttProgres
    rows = (GanttProgres.query.filter_by(plan_id=plan_id)
            .order_by(GanttProgres.data, GanttProgres.id).all())
    # ultima masuratoare <= data de stare, pe cheie (jurnalul e deja sortat crescator)
    pct_curent: dict = {}
    for p in rows:
        if p.data and p.data <= data_stare:
            try:
                pct_curent[p.cheie_activitate] = max(0.0, min(100.0, float(p.procent_fizic or 0)))
            except (TypeError, ValueError):
                pct_curent[p.cheie_activitate] = 0.0
    ev = 0.0
    val_total = 0.0
    for ck, val in valori.items():
        val_total += val
        pct = pct_curent.get(ck, 0.0)
        ev += val * pct / 100.0
    ev_pct = round(100.0 * ev / val_total, 1) if val_total > 0 else 0.0
    return {'ev': round(ev, 2), 'ev_pct': ev_pct,
            'nr_cu_progres': len(pct_curent), 'val_total': round(val_total, 2)}


def _ac_la_data(proiect_id: Optional[int], data_stare: date) -> dict:
    """AC (cost real cumulat) la data de stare. {ac, sursa}.

    Prioritate: manopera pontata + utilaj real (din pontaje/ConsumUtilaj, agregate
    cu functiile existente din services.evm). Fallback documentat: daca nu exista
    nicio inregistrare reala dar exista situatii lunare, foloseste valoarea cumulata
    din ultima situatie <= data de stare. None de cost (proiect lipsa / fara date) ->
    ac=0 cu sursa 'fara' (forecast cade pe varianta atipica in _prognoza).
    """
    if not proiect_id:
        return {'ac': 0.0, 'sursa': 'fara'}
    from services.evm import _pontaje_cumulativ, _utilaj_cumulativ, _man_la_data
    pont_serie, _ = _pontaje_cumulativ(proiect_id)
    util_serie, _ = _utilaj_cumulativ(proiect_id)
    man = _man_la_data(pont_serie, data_stare)      # functie-treapta <= data
    util = _man_la_data(util_serie, data_stare)
    if pont_serie or util_serie:
        return {'ac': round(man + util, 2), 'sursa': 'pontaje+utilaj'}
    # fallback: situatii lunare (valoare cumulata la zi <= data de stare)
    try:
        from models import SituatieLunara
        situatii = (SituatieLunara.query.filter_by(proiect_id=proiect_id)
                    .order_by(SituatieLunara.an, SituatieLunara.luna).all())
        ac = 0.0
        for s in situatii:
            d = s.data_emitere or date(int(s.an or date.today().year),
                                       int(s.luna or 1), 28)
            if d <= data_stare:
                ac = float(s.valoare_cumulat_la_zi or 0)
        if situatii:
            return {'ac': round(ac, 2), 'sursa': 'situatie'}
    except Exception:
        pass
    return {'ac': 0.0, 'sursa': 'fara'}


def evm_pe_plan(plan, tenant_id: Optional[int] = None, data_stare: date = None,
                calendar=None) -> Optional[dict]:
    """EVM la nivel de plan Gantt din tracking, sau None (fara EVM pe plan).

    Intoarce None cand: flag 'gantt-evm-pro' OFF, plan inexistent, plan fara
    baseline activ, sau plan fara progres inregistrat (nimic de masurat).

    Rezultatul e cache-uit pe instanta de plan (`plan._evm_pro_cache`) pe (data de
    stare) - ca sa nu re-rulam agregarea pentru acelasi plan/data in cadrul unui
    request (sectiune UI + endpoint pot cere acelasi rezultat)."""
    if plan is None:
        return None
    if tenant_id is None:
        tenant_id = getattr(plan, 'tenant_id', None)
    if not _flag_on(tenant_id):
        return None
    if data_stare is None:
        data_stare = date.today()

    # cache pe instanta de plan (in-memory, pe request): cheie = data de stare
    cache = getattr(plan, '_evm_pro_cache', None)
    if cache is None:
        cache = {}
        try:
            plan._evm_pro_cache = cache
        except Exception:
            cache = None
    if cache is not None and data_stare in cache:
        return cache[data_stare]

    # baseline activ (snapshot inghetat). Fara baseline -> fara EVM pe plan.
    from services.gantt import tracking_db
    snap = tracking_db.baseline_activ(plan, tenant_id)
    if not snap:
        if cache is not None:
            cache[data_stare] = None
        return None

    # data de start a baseline-ului (pe meta sau pe plan); calendar de lucru optional
    meta = snap.get('meta') or {}
    data_start = None
    ds_meta = meta.get('data_start') or (snap.get('meta') or {}).get('data_start')
    if ds_meta:
        try:
            data_start = date.fromisoformat(str(ds_meta)[:10])
        except (ValueError, TypeError):
            data_start = None
    if data_start is None:
        data_start = getattr(plan, 'data_start', None) or date.today()

    pv_pts, bac, _ = _pv_din_baseline_gantt(snap, data_start, calendar)
    valori = _valori_din_baseline(snap)

    info_ev = _ev_la_data(plan.id, valori, data_stare)
    # plan fara nicio masuratoare de progres <= data de stare -> fara EVM pe plan
    if info_ev['nr_cu_progres'] == 0:
        if cache is not None:
            cache[data_stare] = None
        return None

    info_ac = _ac_la_data(getattr(plan, 'proiect_id', None), data_stare)
    ev = info_ev['ev']
    ac = info_ac['ac']

    from services.evm import _pv_la_data, _prognoza
    pv_pct = _pv_la_data(pv_pts, data_stare)
    pv_val = round(pv_pct / 100.0 * bac, 0)

    spi = round(ev / pv_val, 2) if pv_val else None
    cpi = round(ev / ac, 2) if ac else None
    # forecast (EAC/ETC/VAC/TCPI) - REUTILIZAT din services.evm (nu rescriem formulele)
    prognoza = _prognoza(bac=bac, ev=ev, ac=ac, pv=pv_val)

    status = 'ok'
    if (cpi is not None and cpi < 0.9) or (spi is not None and spi < 0.9):
        status = 'critic'
    elif (cpi is not None and cpi < 1.0) or (spi is not None and spi < 1.0):
        status = 'atentie'

    rezultat = {
        'plan_id': plan.id,
        'plan_nume': plan.nume,
        'data_stare': data_stare.isoformat(),
        'bac': round(bac, 0),
        'pv_pct': round(pv_pct, 1), 'pv_val': pv_val,
        'ev_pct': info_ev['ev_pct'], 'ev_val': round(ev, 0),
        'ac': round(ac, 0), 'ac_sursa': info_ac['sursa'],
        'spi': spi, 'cpi': cpi, 'status': status,
        'nr_activitati_cu_progres': info_ev['nr_cu_progres'],
        'prognoza': prognoza,
        'pv_curba': [{'data': dt.isoformat(), 'procent': round(pr, 1)} for dt, pr in pv_pts],
    }
    if cache is not None:
        cache[data_stare] = rezultat
    return rezultat
