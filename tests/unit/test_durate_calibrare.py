"""Regresie: calibrarea duratelor (garda monetara + potrivire UM + plafon).

Bug-ul reparat: durate patologice in planul consolidat (ex. "Manopera montaj
lifturi 17.500 lei" clasificata CAMINE cu randament 1 buc/zi -> 17.500 zile).
"""

from services.gantt.durate import estimeaza_durata


SETARI = {
    'durata_implicita_zile': 1,
    'durata_max_zile': 240,
    'randamente': {
        'CAMINE': {'randament_zi': 1, 'um': 'buc'},
        'TERMOSISTEM': {'randament_zi': 60, 'um': 'mp'},
        'TAMPLARIE': {'randament_zi': 10, 'um': 'buc'},
        'BETON': {'randament_zi': 30, 'um': 'mc'},
    },
}


def test_um_monetar_da_durata_implicita():
    # 17.500 lei NU inseamna 17.500 camine -> 1 zi, nu 17.500 zile
    assert estimeaza_durata(17500, 'CAMINE', SETARI, um='lei') == 1
    assert estimeaza_durata(10000, 'TERMOSISTEM', SETARI, um='RON') == 1


def test_um_diferit_de_um_randament_da_implicita():
    # cablu in METRI nu se imparte la randament TERMOSISTEM in MP
    assert estimeaza_durata(38250, 'TERMOSISTEM', SETARI, um='m') == 1
    # ancadramente in METRI nu se impart la TAMPLARIE in BUC
    assert estimeaza_durata(1060, 'TAMPLARIE', SETARI, um='m') == 1


def test_um_echivalent_normalizat_trece():
    # m2 == mp, m3 == mc, bucata == buc
    assert estimeaza_durata(600, 'TERMOSISTEM', SETARI, um='m2') == 10   # 600/60
    assert estimeaza_durata(90, 'BETON', SETARI, um='m3') == 3           # 90/30
    assert estimeaza_durata(20, 'TAMPLARIE', SETARI, um='bucata') == 2   # 20/10


def test_plafon_durata_max():
    # cantitate legitima dar uriasa: plafonata la durata_max_zile
    assert estimeaza_durata(100000, 'TERMOSISTEM', SETARI, um='mp') == 240


def test_compatibilitate_fara_um():
    # apel istoric (fara um): comportament neschimbat
    assert estimeaza_durata(600, 'BETON', SETARI) == 20
    assert estimeaza_durata(0, 'BETON', SETARI) == 1
    assert estimeaza_durata(100, None, SETARI) == 1
