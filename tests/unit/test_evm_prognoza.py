"""Teste pentru indicatorii de prognoza EVM (EAC/ETC/VAC/TCPI).

Functia _prognoza e PURA (nu atinge DB) -> teste unit directe pe valori cunoscute.
"""
from services.evm import _prognoza


def test_prognoza_valori_cunoscute():
    # BAC=100k, EV=40k, AC=50k, PV=45k -> CPI = 40/50 = 0.8
    pg = _prognoza(bac=100000, ev=40000, ac=50000, pv=45000)
    # EAC = BAC / CPI = 100000 / 0.8 = 125000
    assert pg['eac'] == 125000
    # ETC = EAC - AC = 125000 - 50000 = 75000
    assert pg['etc'] == 75000
    # VAC = BAC - EAC = 100000 - 125000 = -25000 (depasire de buget)
    assert pg['vac'] == -25000
    # TCPI = (BAC - EV) / (BAC - AC) = 60000 / 50000 = 1.2
    assert pg['tcpi'] == 1.2
    assert pg['eac_varianta'] == 'cpi'


def test_prognoza_sub_buget():
    # CPI > 1 (sub buget): EV=60k, AC=50k -> CPI = 1.2
    pg = _prognoza(bac=100000, ev=60000, ac=50000, pv=55000)
    # EAC = 100000 / 1.2 = 83333.33 -> rotunjit 83333
    assert pg['eac'] == 83333
    # VAC = 100000 - 83333 = 16667 > 0 (economie)
    assert pg['vac'] == 16667
    # TCPI = (100000-60000)/(100000-50000) = 40000/50000 = 0.8 (mai e marja)
    assert pg['tcpi'] == 0.8


def test_prognoza_ac_zero():
    # AC = 0 -> CPI indefinit; cade pe varianta atipica EAC = AC + (BAC - EV)
    pg = _prognoza(bac=100000, ev=0, ac=0, pv=10000)
    # EAC = 0 + (100000 - 0) = 100000
    assert pg['eac'] == 100000
    assert pg['etc'] == 100000          # ETC = EAC - AC = 100000
    assert pg['vac'] == 0               # VAC = BAC - EAC = 0
    assert pg['eac_varianta'] == 'atipica'
    # TCPI = (BAC-EV)/(BAC-AC) = 100000/100000 = 1.0
    assert pg['tcpi'] == 1.0


def test_prognoza_ev_egal_bac():
    # EV = BAC (lucrarea castigata complet); AC sub buget -> CPI valid
    pg = _prognoza(bac=100000, ev=100000, ac=90000, pv=100000)
    # CPI = 100000/90000 = 1.111 -> EAC = 100000/1.111 = 90000
    assert pg['eac'] == 90000
    # TCPI = (BAC-EV)/(BAC-AC) = 0 / 10000 = 0.0 (nu mai e nimic de castigat)
    assert pg['tcpi'] == 0.0


def test_prognoza_ac_egal_bac_tcpi_divizor_zero():
    # AC = BAC -> bugetul ramas (BAC - AC) = 0 -> TCPI = None (diviziune cu 0)
    pg = _prognoza(bac=100000, ev=80000, ac=100000, pv=90000)
    assert pg['tcpi'] is None
    # EAC = BAC / CPI; CPI = 80000/100000 = 0.8 -> EAC = 125000
    assert pg['eac'] == 125000


def test_prognoza_toate_zero():
    # Robust la lipsa totala de date (proiect gol) -> fara exceptii
    pg = _prognoza(bac=0, ev=0, ac=0, pv=0)
    assert pg['eac'] == 0 and pg['etc'] == 0 and pg['vac'] == 0
    assert pg['tcpi'] is None
    assert pg['eac_varianta'] == 'atipica'
