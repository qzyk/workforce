"""
Teste unitare pentru services/audit_deviz.py.

Construiesc seturi sintetice .xlsx in memorie (citite prin acelasi
import_engine._citeste_sheeturi ca in productie) si verific:
  - clasificarea fisierelor + cheia de obiect (sare prefixul de disciplina)
  - reconcilierea 3 niveluri (F3 == C6+C7+C8+C9, Sigma F3 == F2)
  - structura de cost
  - detectia anomaliilor (transport 0, tarif uniform, discrepanta L2)
"""
import io

from openpyxl import Workbook

from services.audit_deviz import analizeaza_set, cheie_obiect, clasifica_fisier


def _xlsx(rows) -> bytes:
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _set_ok():
    """Set coerent: 1 obiect, F3=1000 = C6(800)+C7(200), F2 declara 1000."""
    f2 = _xlsx([
        ['CENTRALIZATOR'],
        ['Nr', 'Cap', 'Cheltuieli', 'Valoare'],
        ['', '', '01 LUCRARI LA FATADE', 1000],
        ['TOTAL 004 ARHITECTURA (fara TVA)', '', '', 1000],
        ['TVA (21.00%)', '', '', 210],
        ['TOTAL 004 ARHITECTURA (cu TVA)', '', '', 1210],
    ])
    f3 = _xlsx([
        ['Formular F3'],
        ['Nr', 'Capitol', 'U.M.', 'Cantitate', 'Pret', 'TOTAL'],
        [1, 'Lucrare X', 'mp', 10, 80, 800],
        ['TOTAL GENERAL (fara TVA)', '', '', 1000, '', ''],
        ['TVA (21.00%)', '', '', 210, '', ''],
        ['TOTAL GENERAL (inclusiv TVA)', '', '', 1210, '', ''],
    ])
    c6 = _xlsx([
        ['Formular C6 Lista cuprinzand resurse materiale'],
        ['Nr', 'Denumirea resursei materiale', 'U.M.', 'Consum', 'Pret unitar', 'Valoare'],
        [1, '600001 - Ciment', 'kg', 100, 5, 500],
        [2, '600002 - Nisip', 'mc', 10, 30, 300],
        ['TOTAL Materiale', '', '', '', '', 800],
    ])
    c7 = _xlsx([
        ['Formular C7 mana de lucru'],
        ['Nr', 'Denumirea meseriei', 'Consum Om/ore', 'Tarif', 'Valoare'],
        [1, '31100 - Zugrav', 5, 30, 150],
        [2, '31000 - Zidar', 1.67, 30, 50],
        ['Ore Manopera', '', 6.67, 'TOTAL', 200],
    ])
    return [
        ('004_ARHITECTURA_F2_centralizator.xlsx', f2),
        ('004_01_LUCRARI_LA_FATADE_F3_lista.xlsx', f3),
        ('004_01_LUCRARI_LA_FATADE_C6_materiale.xlsx', c6),
        ('004_01_LUCRARI_LA_FATADE_C7_manopera.xlsx', c7),
    ]


def test_clasificare_si_cheie_obiect():
    assert clasifica_fisier('004_01_X_F3_lista.xls') == 'F3'
    assert clasifica_fisier('004_ARHITECTURA_F2_centralizator.xls') == 'F2'
    assert clasifica_fisier('citeste-ma.txt') is None
    num, nume = cheie_obiect('004_01_LUCRARI_LA_FATADE_F3_lista.xls')
    assert num == '01'  # obiectul, NU disciplina "004"
    assert 'Lucrari' in nume


def test_reconciliere_si_structura_cost():
    rez = analizeaza_set(_set_ok())
    assert rez['nr_obiecte'] == 1
    assert rez['total_f3'] == 1000
    assert rez['total_f2'] == 1000
    o = rez['obiecte'][0]
    assert o['numar'] == '01'
    assert o['c6'] == 800 and o['c7'] == 200
    assert abs(o['delta_l2']) < 1          # F3 == C6+C7+C8+C9
    assert o['status'] == 'ok'
    assert round(rez['pct_material']) == 80
    assert round(rez['pct_manopera']) == 20


def test_anomalii_transport_si_tarif_uniform():
    rez = analizeaza_set(_set_ok())
    tipuri = {a['tip'] for a in rez['anomalii']}
    assert 'transport_zero' in tipuri      # C9 = 0 peste tot
    assert 'tarif_uniform' in tipuri       # tot 30 lei/ora


def test_detecteaza_discrepanta_l2():
    files = [f for f in _set_ok() if '_C7_' not in f[0]]
    bad_c7 = _xlsx([
        ['Formular C7 mana de lucru'],
        ['Nr', 'Denumirea meseriei', 'Consum Om/ore', 'Tarif', 'Valoare'],
        [1, '31100 - Zugrav', 2, 30, 60],
        ['Ore Manopera', '', 2, 'TOTAL', 60],
    ])
    files.append(('004_01_LUCRARI_LA_FATADE_C7_manopera.xlsx', bad_c7))
    rez = analizeaza_set(files)
    o = rez['obiecte'][0]
    # f3=1000, c6=800, c7=60 -> delta_l2 = 140 (14%) -> critic
    assert o['status'] == 'critic'
    assert 'reconciliere_l2' in {a['tip'] for a in rez['anomalii']}
