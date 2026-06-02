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


def calculeaza_cost(art, categorie, tarife: dict, preturi_boq: dict = None) -> tuple:
    """Intoarce (valoare, valoare_material, valoare_manopera, valoare_utilaj, cost_estimat).

    Prioritate: pret real din deviz (BoQ, match pe cod articol apoi denumire) >
    pret din F3 > cantitate x tarif(categorie) [estimare].

    Descompunere pe 3 resurse (material / manopera / utilaj):
    - daca exista descompunere explicita (deviz sau preturi unitare F3) o foloseste;
    - altfel imparte valoarea pe ponderile categoriei (material/utilaj; restul=manopera).
      Pondere utilaj implicita 0 -> rezultat identic cu varianta veche (2 resurse)."""
    t = (tarife or {}).get(categorie or '', {}) or {}
    pondere_mat = min(max(float(t.get('material', 0.65) or 0.65), 0.0), 1.0)
    pondere_uti = min(max(float(t.get('utilaj', 0.0) or 0.0), 0.0), 1.0)
    if pondere_mat + pondere_uti > 1.0:                  # normalizeaza daca depasesc
        pondere_uti = max(0.0, 1.0 - pondere_mat)
    cant = float(art.cantitate or 0)

    def _split(val):
        """(material, manopera, utilaj) impartind val pe ponderi; restul = manopera."""
        m = val * pondere_mat
        u = val * pondere_uti
        return m, max(0.0, val - m - u), u

    # 0. pret REAL din deviz pretuit (BoQ) - nu e estimare
    if preturi_boq:
        from .normalizare import normalizeaza, normalizeaza_cheie
        rec = (preturi_boq.get('cod', {}).get(normalizeaza_cheie(art.cod_articol or ''))
               or preturi_boq.get('den', {}).get(normalizeaza(art.denumire or '')))
        if rec and rec.get('pu', 0) > 0:
            val = cant * float(rec['pu'])
            mat = cant * float(rec.get('mat') or 0)
            man = cant * float(rec.get('man') or 0)
            uti = cant * float(rec.get('uti') or 0)
            if mat + man + uti <= 0:                     # deviz fara descompunere -> ponderi
                mat, man, uti = _split(val)
            return round(val, 2), round(mat, 2), round(man, 2), round(uti, 2), False

    estimat = False
    if art.pret_total and art.pret_total > 0:
        val = float(art.pret_total)
    elif art.pret_unitar and art.pret_unitar > 0:
        val = cant * float(art.pret_unitar)
    else:
        val = cant * float(t.get('tarif', 0) or 0)
        estimat = True

    # descompunere din preturile unitare F3 (material/manopera/utilaj), daca exista
    mat = man = uti = 0.0
    if not estimat and (art.pret_material or art.pret_manopera
                        or getattr(art, 'pret_utilaj', 0)):
        mat = cant * float(art.pret_material or 0)
        man = cant * float(art.pret_manopera or 0)
        uti = cant * float(getattr(art, 'pret_utilaj', 0) or 0)
    if mat + man + uti <= 0:
        mat, man, uti = _split(val)

    return round(val, 2), round(mat, 2), round(man, 2), round(uti, 2), estimat
