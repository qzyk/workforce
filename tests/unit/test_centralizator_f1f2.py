"""Teste pentru parserele F1/F2 + total F3 (reconciliere obiectiv).

Nuclee pure pe randuri (list[list]) - fara fisiere, fara DB.
"""

from decimal import Decimal

from services.parsers import centralizator_f1f2 as cf


F1_ROWS = [
    ['CENTRALIZATORUL cheltuielilor'],
    [],
    ['Nr.', 'Nr. cap. Deviz General', 'Denumirea capitolelor', '', 'Valoare (fara TVA)', '', 'Din care C+M'],
    ['', '', '', '', 'Lei', '', 'Lei'],
    ['0', '1', '2', '', '3', '', '4'],
    ['6.1', '4.1', 'Constructii si instalatii', '', '23887240.24', '', '23887240.24'],
    ['', '', '001 Arhitectura', '', '7124361.82', '', '7124361.82'],
    ['', '', '002 Structura', '', '13749108.70', '', '13749108.70'],
    ['', '', '003 Instalatii', '', '3013769.72', '', '3013769.72'],
    ['6.2', '4.2', 'Montaj utilaje', '', '134380.94', '', '134380.94'],
    ['', '', '003 Montaj lifturi', '', '11010.42', '', '11010.42'],
]

F2_ROWS = [
    ['CENTRALIZATORUL cheltuielilor'],
    [],
    ['Nr.', 'Nr cap. Deviz General', 'Cheltuieli pe categorii', '', '', 'Valoare (fara TVA)'],
    ['', '', '', '', '', 'Lei'],
    ['0', '1', '2', '', '', '3'],
    ['CAPITOL I I. Constructii'],
    ['2', '4.1.1', 'Terasamente', '', '', '0.0'],
    ['4', '4.1.3', 'Arhitectura', '', '', '7124361.82'],
    ['', '', '001 Arhitectura c2 - Lucrari desfacere', '', '', '733609.51'],
    ['', '', '002 Arhitectura c2 - Lucrari noi', '', '', '6390752.31'],
    ['CAPITOL II II. Montaj'],
    ['', '', '003 Montaj lifturi', '', '', '11010.42'],
]

F3_ROWS = [
    ['Formular F3 Lista cu cantitati'],
    ['SECTIUNEA TEHNICA', '', '', '', '', 'SECTIUNEA FINANCIARA'],
    ['Nr.', 'Capitol de lucrari', 'U.M.', 'Cantitatea', '', 'Pretul unitar', 'TOTALUL (fara TVA)'],
    ['0', '1', '2', '3', '', '4', '5 = 3 x 4'],
    ['PARDOSELI'],
    ['1', 'CG01A - Strat suport', 'mp', '397.0', '', '61.01', '24220.60'],
    ['', '', '', 'material:', '', '25.88', '10275.88'],
    ['', '', '', 'manopera:', '', '24.54', '9741.39'],
    ['2', 'CG01E - Strat', 'mp', '2110.0', '', '46.23', '97537.00'],
    ['', '', '', 'material:', '', '33.64', '70986.16'],
]


def test_parse_f1_obiecte_si_valoare():
    rez = cf.parse_f1(F1_ROWS)
    obiecte = {o['cod']: o for o in rez['obiecte']}
    # primele 3 obiecte (constructii)
    assert obiecte['001']['valoare'] == Decimal('7124361.82')
    assert obiecte['001']['nume'] == 'Arhitectura'
    assert obiecte['002']['valoare'] == Decimal('13749108.70')
    # C+M citit din coloana corecta
    assert obiecte['002']['cm'] == Decimal('13749108.70')
    # total 4.1 detectat
    assert rez['total_4_1'] == Decimal('23887240.24')
    # 003 apare de 2 ori (constructii + montaj) -> ambele linii prezente
    coduri = [o['cod'] for o in rez['obiecte']]
    assert coduri.count('003') == 2


def test_parse_f2_sub_obiecte():
    rez = cf.parse_f2(F2_ROWS)
    sub = {s['cod']: s for s in rez['sub_obiecte']}
    assert sub['001']['valoare'] == Decimal('733609.51')
    assert sub['002']['valoare'] == Decimal('6390752.31')
    assert sub['003']['valoare'] == Decimal('11010.42')
    # totalul = suma sub-obiectelor
    assert rez['total'] == Decimal('733609.51') + Decimal('6390752.31') + Decimal('11010.42')


def test_total_f3_sare_subrandurile_si_antetul():
    total, n = cf.total_f3_rows(F3_ROWS)
    # doar 2 articole (randurile cu Nr 1 si 2), nu sub-randurile material:/manopera:
    assert n == 2
    assert total == Decimal('24220.60') + Decimal('97537.00')


def test_detectie_coloana_valoare_toleranta():
    # coloana valoare pe pozitie diferita (F1 vs F2) - detectata din antet
    idx_val_f1, idx_cm_f1 = cf._gaseste_coloane(F1_ROWS)
    idx_val_f2, idx_cm_f2 = cf._gaseste_coloane(F2_ROWS)
    assert idx_val_f1 == 4 and idx_cm_f1 == 6
    assert idx_val_f2 == 5 and idx_cm_f2 is None
