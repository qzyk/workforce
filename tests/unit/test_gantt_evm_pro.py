"""
Teste unitare pentru EVM pe plan din tracking (Gantt Faza 3) - functii PURE:
- _pv_din_baseline_gantt: curba S (zi-based) din snapshot -> [(date, procent)] + BAC
- _valori_din_baseline: valori inghetate pe cheie (ponderea EV)
- reutilizarea forecast-ului din services.evm._prognoza (NU rescriem formulele)

Nu necesita Flask/DB: testeaza direct functiile pure peste dict-uri de snapshot.
Partea cu DB (jurnal progres, AC, gating flag) e in integration/test_gantt_evm_pro.py.
"""
from datetime import date

from services.gantt import evm_pro
from services.evm import _prognoza


def _snapshot():
    """Snapshot baseline minimal (forma tracking.snapshot_baseline): 2 activitati,
    curba S pe 10 zile, BAC = 1000 (600 + 400)."""
    return {
        'activitati': {
            'cheieA': {'valoare': 600.0, 'start_zi': 0, 'finish_zi': 5, 'durata': 5},
            'cheieB': {'valoare': 400.0, 'start_zi': 5, 'finish_zi': 10, 'durata': 5},
        },
        'curba_s': [
            {'zi': 5, 'cumulat': 600.0, 'procent': 60.0},
            {'zi': 10, 'cumulat': 1000.0, 'procent': 100.0},
        ],
        'meta': {'bac': 1000.0, 'durata_zile': 10, 'nr_activitati': 2},
    }


# ------------------------------------------------------------- PV din baseline
def test_pv_din_baseline_mapeaza_zi_pe_data():
    """Curba S 1-based (zi=5,10) -> date lucratoare reale pornind de la data de start."""
    snap = _snapshot()
    # start luni 2026-06-01; fara calendar -> doar Lu-Vi
    pts, bac, ds = evm_pro._pv_din_baseline_gantt(snap, date(2026, 6, 1))
    assert bac == 1000.0
    assert len(pts) == 2
    # zi 5 (index 4) = a 5-a zi lucratoare = vineri 2026-06-05; procent 60
    assert pts[0] == (date(2026, 6, 5), 60.0)
    # zi 10 (index 9) = a 10-a zi lucratoare = vineri 2026-06-12; procent 100
    assert pts[1] == (date(2026, 6, 12), 100.0)


def test_pv_din_baseline_gol_la_curba_lipsa():
    """Snapshot fara curba S sau durata 0 -> PV gol (dar BAC din meta)."""
    pts, bac, _ = evm_pro._pv_din_baseline_gantt(
        {'curba_s': [], 'meta': {'bac': 500.0, 'durata_zile': 0}}, date(2026, 6, 1))
    assert pts == [] and bac == 500.0


# ------------------------------------------------------------- valori inghetate
def test_valori_din_baseline():
    valori = evm_pro._valori_din_baseline(_snapshot())
    assert valori == {'cheieA': 600.0, 'cheieB': 400.0}


def test_valori_din_baseline_robust_la_valoare_lipsa():
    snap = {'activitati': {'x': {'valoare': None}, 'y': {}}}
    assert evm_pro._valori_din_baseline(snap) == {'x': 0.0, 'y': 0.0}


# ------------------------------------------------------------- forecast reutilizat
def test_forecast_reutilizeaza_prognoza_evm():
    """EVM pe plan foloseste EXACT services.evm._prognoza pentru EAC/ETC/VAC/TCPI.

    Scenariu: BAC=1000, EV=600 (60% realizat), AC=750 (cost mai mare), PV=600.
    CPI = 600/750 = 0.8 -> EAC = BAC/CPI = 1250; ETC = 1250-750 = 500;
    VAC = 1000-1250 = -250; TCPI = (1000-600)/(1000-750) = 1.6.
    """
    p = _prognoza(bac=1000.0, ev=600.0, ac=750.0, pv=600.0)
    assert p['eac'] == 1250.0
    assert p['etc'] == 500.0
    assert p['vac'] == -250.0
    assert p['tcpi'] == 1.6
    assert p['eac_varianta'] == 'cpi'


def test_forecast_fara_cost_real_varianta_atipica():
    """AC=0 (niciun cost real inca) -> EAC atipica = AC + (BAC - EV)."""
    p = _prognoza(bac=1000.0, ev=600.0, ac=0.0, pv=600.0)
    assert p['eac'] == 400.0          # 0 + (1000 - 600)
    assert p['eac_varianta'] == 'atipica'
    # rest buget = BAC - AC = 1000 -> TCPI = (1000 - 600) / 1000 = 0.4
    assert p['tcpi'] == 0.4
