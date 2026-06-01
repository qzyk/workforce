"""
Cost (5D) pentru o activitate de planificare.

Prioritatea valorii:
  1. pret_total din F3 (daca e completat)
  2. cantitate x pret_unitar din F3
  3. cantitate x tarif(categorie)  -> ESTIMARE (cost_estimat=True)

Descompunere material/manopera:
  - din coloanele de pret unitar material/manopera (F3), daca exista;
  - altfel pe ponderea de material configurata pe categorie (tarife.json / DB).
"""
from __future__ import annotations


def calculeaza_cost(art, categorie, tarife: dict) -> tuple:
    """Intoarce (valoare, valoare_material, valoare_manopera, cost_estimat)."""
    t = (tarife or {}).get(categorie or '', {}) or {}
    pondere_mat = float(t.get('material', 0.65) or 0.65)
    pondere_mat = min(max(pondere_mat, 0.0), 1.0)
    cant = float(art.cantitate or 0)

    estimat = False
    if art.pret_total and art.pret_total > 0:
        val = float(art.pret_total)
    elif art.pret_unitar and art.pret_unitar > 0:
        val = cant * float(art.pret_unitar)
    else:
        val = cant * float(t.get('tarif', 0) or 0)
        estimat = True

    # descompunere material/manopera
    mat = man = 0.0
    if not estimat and (art.pret_material or art.pret_manopera):
        mat = cant * float(art.pret_material or 0)
        man = cant * float(art.pret_manopera or 0)
    if mat + man <= 0:
        mat = val * pondere_mat
        man = val * (1.0 - pondere_mat)

    return round(val, 2), round(mat, 2), round(man, 2), estimat
