"""
Serviciu pentru calculul orelor de pontaj si al sporurilor.

Extrage logica de calcul ore (detectie tip_zi + ore normale / suplimentare
50% / 100%) din routes/pontaje.py intr-un loc reutilizabil, fara a-i schimba
comportamentul. In plus, adauga calculul orelor de noapte (intervalul legal
22:00-06:00), folosit pentru sporul de noapte (min 25% conform Codului Muncii).

Reguli importante:
- `calcul_ore(...)` este o functie PURA: nu cunoaste si nu consulta feature
  flags. Comportamentul ei pe orele normale / suplimentare este IDENTIC cu
  vechea `calculate_hours` din routes/pontaje.py.
- Sporul de noapte se include doar daca apelantul cere explicit
  (`include_spor_noapte=True`). Cu valoarea implicita (False), rezultatul
  contine `spor_noapte=None`, deci comportamentul istoric e pastrat 1:1.
- Detectia turei de noapte (ora_sfarsit < ora_start) urmeaza acelasi tipar ca
  in model (models.Pontaj), dar fereastra legala 22:00-06:00 e calculata pe
  minut, nu doar pe "este tura de noapte da/nu".

Folosire (in rute, gated pe flag-ul 'pontaj-spor-noapte'):

    from services.sporuri import calcul_ore
    from services.feature_flags import is_enabled

    rezultat = calcul_ore(ora_start, ora_sfarsit, tip_zi, data_pontaj,
                          include_spor_noapte=is_enabled('pontaj-spor-noapte'))
"""

from __future__ import annotations

from typing import Optional


# Procentul minim legal pentru sporul de noapte (Codul Muncii: min 25%).
# Expus ca referinta pentru calculul valoric (in afara acestui serviciu);
# aici se intoarce doar numarul de ore de noapte (baza sporului).
PROCENT_SPOR_NOAPTE_MIN = 25

# Limita zilnica de ore (identica cu vechea logica din routes/pontaje.py).
_LIMITA_ORE_ZI = 12 * 60
# Pauza de masa dedusa daca se lucreaza peste 6h.
_PRAG_PAUZA_MASA = 6 * 60
_PAUZA_MASA_MIN = 30


def _parse_ore(ora_start, ora_sfarsit):
    """
    Parseaza 'HH:MM' -> (minut_start, minut_sfarsit, total_min).

    Intoarce None daca formatul e invalid (acelasi guard ca in vechea functie).
    `total_min` include corectia pentru tura de noapte (+24h cand <= 0).
    """
    try:
        h1, m1 = map(int, ora_start.split(':'))
        h2, m2 = map(int, ora_sfarsit.split(':'))
    except (ValueError, AttributeError):
        return None

    start_min = h1 * 60 + m1
    end_min = h2 * 60 + m2
    total_min = end_min - start_min
    if total_min <= 0:
        total_min += 24 * 60  # tura de noapte
    return start_min, end_min, total_min


def _minute_de_noapte(start_min: int, total_min: int) -> int:
    """
    Calculeaza minutele lucrate in fereastra legala de noapte (22:00-06:00).

    Tura e modelata ca interval continuu [start_min, start_min + total_min)
    pe o axa de timp care poate depasi 24h (tura peste miezul noptii).
    Fereastra de noapte se repeta zilnic: [00:00-06:00] si [22:00-24:00],
    adica, raportat la o zi de 1440 min: [0, 360) si [1320, 1440).

    Verificam intersectia turei cu ferestrele de noapte pentru ziua curenta
    si ziua urmatoare (suficient: o tura e limitata la max 12h mai jos, deci
    nu poate atinge a treia fereastra).
    """
    if total_min <= 0:
        return 0

    inceput = start_min
    sfarsit = start_min + total_min

    total_noapte = 0
    # Ferestrele de noapte pentru ziua 0 si ziua 1 (offset cu 1440 min).
    for offset in (0, 24 * 60):
        ferestre = (
            (offset + 0, offset + 6 * 60),        # 00:00 - 06:00
            (offset + 22 * 60, offset + 24 * 60),  # 22:00 - 24:00
        )
        for f_start, f_end in ferestre:
            lo = max(inceput, f_start)
            hi = min(sfarsit, f_end)
            if hi > lo:
                total_noapte += hi - lo
    return total_noapte


def este_tura_noapte(ora_start, ora_sfarsit) -> bool:
    """
    True daca tura atinge fereastra legala de noapte (22:00-06:00).

    Util pentru decizii simple (afisare/etichetare) fara a calcula orele.
    """
    parsed = _parse_ore(ora_start, ora_sfarsit)
    if parsed is None:
        return False
    start_min, _end_min, total_min = parsed
    # Aplicam aceeasi limita de 12h ca la calculul orelor, pentru consistenta.
    total_min = min(total_min, _LIMITA_ORE_ZI)
    return _minute_de_noapte(start_min, total_min) > 0


def calcul_ore(ora_start, ora_sfarsit, tip_zi, data_pontaj=None,
               include_spor_noapte: bool = False) -> dict:
    """
    Calculeaza orele lucrate conform legislatiei constructiilor.

    Comportament IDENTIC cu vechea routes.pontaje.calculate_hours pe cheile:
    ore_lucrate, ore_normale, ore_supl_50, ore_supl_100, tip_zi.

    In plus intoarce cheia 'spor_noapte':
    - None cand include_spor_noapte=False (comportament istoric) sau cand
      formatul orelor e invalid;
    - numarul de ore din fereastra 22:00-06:00 (rotunjit la 2 zecimale) cand
      include_spor_noapte=True (baza pentru sporul de noapte, min 25%).

    Importarea modelului (SarbatoareLegala) se face lazy ca serviciul sa nu
    creeze dependente la incarcare si sa ramana usor de testat.
    """
    parsed = _parse_ore(ora_start, ora_sfarsit)
    if parsed is None:
        return {
            'ore_lucrate': 0,
            'ore_normale': 0,
            'ore_supl_50': 0,
            'ore_supl_100': 0,
            'spor_noapte': None,
        }

    start_min, _end_min, total_min = parsed

    # Limita 12h/zi
    if total_min > _LIMITA_ORE_ZI:
        total_min = _LIMITA_ORE_ZI

    # Orele de noapte se calculeaza pe intervalul efectiv lucrat (dupa limita
    # de 12h), INAINTE de deducerea pauzei de masa, pentru a reflecta timpul
    # petrecut in fereastra 22:00-06:00.
    minute_noapte = _minute_de_noapte(start_min, total_min)

    # Pauza masa 30 min dedusa daca > 6h
    if total_min > _PRAG_PAUZA_MASA:
        total_min -= _PAUZA_MASA_MIN

    ore_lucrate = round(total_min / 60, 2)

    # Detectie sarbatoare legala (lazy import - acelasi efect ca vechea logica)
    is_sarbatoare = False
    if data_pontaj:
        from models import SarbatoareLegala
        is_sarbatoare = SarbatoareLegala.query.filter_by(data=data_pontaj).first() is not None

    # Detectie tip zi automat din data
    if data_pontaj and tip_zi == 'lucratoare':
        dow = data_pontaj.weekday()  # 0=Lu, 5=Sa, 6=Du
        if is_sarbatoare:
            tip_zi = 'sarbatoare_legala'
        elif dow == 5:
            tip_zi = 'sambata'
        elif dow == 6:
            tip_zi = 'duminica'

    # Calcul ore
    ore_normale = 0
    ore_supl_50 = 0
    ore_supl_100 = 0

    if tip_zi in ('duminica', 'sarbatoare_legala'):
        # Toate orele sunt 100%
        ore_supl_100 = ore_lucrate
    elif tip_zi == 'sambata':
        # Toate orele sambata sunt 50%
        ore_supl_50 = ore_lucrate
    elif tip_zi in ('co', 'cm', 'invoiere'):
        # Tipuri speciale - nu se calculeaza ore suplimentare
        ore_normale = ore_lucrate
    else:
        # Zi lucratoare normala
        ore_normale = min(8, ore_lucrate)
        extra = max(0, ore_lucrate - 8)
        if extra > 0:
            # Ore 8-10 = 50%, ore > 10 = 100%
            ore_supl_50 = min(2, extra)
            ore_supl_100 = max(0, extra - 2)

    # Sporul de noapte: baza in ore (fereastra 22:00-06:00). Doar cand cerut.
    spor_noapte = None
    if include_spor_noapte:
        spor_noapte = round(minute_noapte / 60, 2)

    return {
        'ore_lucrate': ore_lucrate,
        'ore_normale': round(ore_normale, 2),
        'ore_supl_50': round(ore_supl_50, 2),
        'ore_supl_100': round(ore_supl_100, 2),
        'tip_zi': tip_zi,
        'spor_noapte': spor_noapte,
    }


def detecteaza_tip_zi(data_pontaj) -> str:
    """
    Detecteaza automat tipul zilei (lucratoare / sambata / duminica /
    sarbatoare_legala) pe baza datei. Identic cu vechea _detect_tip_zi.
    """
    if not data_pontaj:
        return 'lucratoare'
    from models import SarbatoareLegala
    is_sarb = SarbatoareLegala.query.filter_by(data=data_pontaj).first()
    if is_sarb:
        return 'sarbatoare_legala'
    dow = data_pontaj.weekday()
    if dow == 5:
        return 'sambata'
    elif dow == 6:
        return 'duminica'
    return 'lucratoare'
