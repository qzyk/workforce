"""
Estimarea duratelor activitatilor.

Durata (zile lucratoare) = ceil(cantitate / randament_pe_zi) pentru categoria tehnologica,
cu minim 1 zi. Randamentele sunt configurabile (config/gantt/setari.json -> randamente).
Se foloseste durata implicita cand:
  - nu exista randament pentru categorie sau cantitatea e 0;
  - UM-ul articolului e monetar (lei/ron/eur) - banii nu sunt cantitate fizica
    (ex. "Manopera montaj lifturi 17.500 lei" NU inseamna 17.500 bucati);
  - UM-ul articolului difera de UM-ul declarat al randamentului (nu impartim
    metri liniari la un randament exprimat in mp/zi sau buc/zi).
Plafon de sanitate optional: setari['durata_max_zile'] - o activitate nu poate
depasi plafonul (in realitate se suplimenteaza echipa), ca un singur articol
patologic sa nu deformeze tot programul.

Aici se poate conecta ulterior modulul de norme de productivitate existent (planificare_bim).
"""
from __future__ import annotations

import math
from typing import Optional


# UM-uri monetare: cantitatea e valoare, nu masura fizica -> durata implicita
_UM_MONETARE = {'lei', 'ron', 'eur', 'euro', 'usd'}

# Normalizare UM: variante echivalente -> forma canonica
_UM_CANONIC = {
    'm2': 'mp', 'm.p.': 'mp', 'm.p': 'mp',
    'm3': 'mc', 'm.c.': 'mc', 'm.c': 'mc',
    'ml': 'm', 'm.l.': 'm', 'm.l': 'm',
    'bucata': 'buc', 'bucati': 'buc', 'buc.': 'buc', 'bc': 'buc',
    'tona': 'to', 'tone': 'to', 't': 'to',
    'kilogram': 'kg', 'kgr': 'kg',
    'ora': 'ore', 'h': 'ore',
}


def _norm_um(um) -> str:
    s = str(um or '').strip().lower().rstrip('.')
    return _UM_CANONIC.get(s, s)


def estimeaza_durata(cantitate: float, categorie: Optional[str], setari: dict,
                     um: Optional[str] = None) -> int:
    """Intoarce durata in zile (int, minim 1).

    `um` (optional) = UM-ul articolului; cand e dat, activeaza garda monetara
    si potrivirea cu UM-ul randamentului. Fara `um`, comportamentul ramane
    cel istoric (cantitate / randament).
    """
    implicita = max(1, int(setari.get('durata_implicita_zile', 1) or 1))
    randamente = setari.get('randamente', {})
    if not categorie or categorie not in randamente:
        return implicita

    um_art = _norm_um(um) if um else ''
    if um_art in _UM_MONETARE:
        return implicita

    randament = randamente[categorie].get('randament_zi', 0) or 0
    if randament <= 0 or not cantitate or cantitate <= 0:
        return implicita

    um_rand = _norm_um(randamente[categorie].get('um'))
    if um_art and um_rand and um_art != um_rand:
        return implicita

    zile = max(1, math.ceil(float(cantitate) / float(randament)))
    plafon = int(setari.get('durata_max_zile', 0) or 0)
    if plafon > 0:
        zile = min(zile, plafon)
    return zile
