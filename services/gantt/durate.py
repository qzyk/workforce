"""
Estimarea duratelor activitatilor.

Durata (zile lucratoare) = ceil(cantitate / randament_pe_zi) pentru categoria tehnologica,
cu minim 1 zi. Randamentele sunt configurabile (config/gantt/setari.json -> randamente).
Daca nu exista randament pentru categorie sau cantitatea e 0, se foloseste durata implicita.

Aici se poate conecta ulterior modulul de norme de productivitate existent (planificare_bim).
"""
from __future__ import annotations

import math
from typing import Optional


def estimeaza_durata(cantitate: float, categorie: Optional[str], setari: dict) -> int:
    """Intoarce durata in zile (int, minim 1)."""
    implicita = int(setari.get('durata_implicita_zile', 1) or 1)
    randamente = setari.get('randamente', {})
    if not categorie or categorie not in randamente:
        return max(1, implicita)
    randament = randamente[categorie].get('randament_zi', 0) or 0
    if randament <= 0 or not cantitate or cantitate <= 0:
        return max(1, implicita)
    zile = math.ceil(float(cantitate) / float(randament))
    return max(1, int(zile))
