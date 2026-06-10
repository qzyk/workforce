"""Regresie: import F3 cu antetul 'Capitol de lucrari' (layout SICAP real,
ex. Academia de Politie) prin setarile IMPLICITE (fluxul batch/CLI).

Bug-ul reparat: SETARI_IMPLICITE din config_loader era desincronizat de
config/gantt/setari.json - fara sinonimul 'capitol de lucrari' la denumire
si fara coloanele pret_* . UI-ul mergea (store.setari() citeste json-ul),
dar importa_din_cale()/importa() cu setari=None pica la detectia antetului,
iar preturile nu se mapau.
"""
import io

from services.gantt import import_engine
from services.gantt.config_loader import SETARI_IMPLICITE


# Layout-ul real: antet pe randul 2, rand de numerotare, titlu de sectiune,
# articole cu sub-randuri material:/manopera:/utilaj:/transport:
_RANDURI_ACADEMIA = [
    ['Formular F3 Lista cu cantitati', '', '', '', '', '', ''],
    ['SECTIUNEA TEHNICA', '', '', '', '', 'SECTIUNEA FINANCIARA', ''],
    ['Nr.', 'Capitol de lucrari', 'U.M.', 'Cantitatea', '',
     'Pretul unitar\n(fara TVA)\n- Lei -', 'TOTALUL\n(fara TVA)\n- Lei -'],
    ['0', '1', '2', '3', '', '4', '5 = 3 x 4'],
    ['PARDOSELI', '', '', '', '', '', ''],
    ['1', 'CG01A-15# - Strat suport pardoseli', 'mp', 397, '', 61.01, 24220.60],
    ['', '', '', 'material:', '', 25.88, 10275.88],
    ['', '', '', 'manopera:', '', 24.54, 9741.39],
    ['', '', '', 'utilaj:', '', 10.59, 4203.33],
    ['', '', '', 'transport:', '', 0, 0],
    ['2', 'CG01E# - Strat suport nisip', 'mp', 2110, '', 46.23, 97537.00],
    ['', '', '', 'material:', '', 33.64, 70986.16],
    ['', '', '', 'manopera:', '', 12.58, 26550.84],
    ['', '', '', 'utilaj:', '', 0, 0],
    ['', '', '', 'transport:', '', 0, 0],
]


def _xlsx_academia() -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    for r in _RANDURI_ACADEMIA:
        ws.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_setari_implicite_sincronizate_cu_json():
    """Fallback-ul hardcodat trebuie sa stie 'capitol de lucrari' + coloanele pret_*."""
    col = SETARI_IMPLICITE['coloane']
    assert 'capitol de lucrari' in col['denumire']
    for camp in ('pret_unitar', 'pret_material', 'pret_manopera',
                 'pret_utilaj', 'pret_total'):
        assert camp in col, f'lipseste {camp} din SETARI_IMPLICITE'


def test_import_antet_capitol_de_lucrari_cu_setari_default():
    """Antetul 'Capitol de lucrari' e gasit FARA setari explicite (fluxul CLI)."""
    articole, raport = import_engine.importa(_xlsx_academia(), '.xlsx')
    assert raport['nr_articole'] == 2
    a1, a2 = articole
    assert 'Strat suport pardoseli' in a1.denumire
    assert a1.cantitate == 397
    # preturile mapate (inainte de fix ieseau 0 pe acest flux)
    assert a1.pret_unitar == 61.01
    assert a1.pret_total == 24220.60
    # sub-randurile material:/manopera: agregate pe articol, nu articole separate
    assert a1.pret_material == 25.88
    assert a1.pret_manopera == 24.54
    assert a1.pret_utilaj == 10.59
    assert a2.pret_material == 33.64
    # titlul de sectiune devine context, nu articol
    assert all('PARDOSELI' != a.denumire for a in articole)
