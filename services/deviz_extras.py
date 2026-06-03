"""
Parser pentru extrasele de resurse din deviz (Formular C6/C7/C8).

Detecteaza automat tipul din antet ("Formular C6/C7/C8" sau cuvinte-cheie) si
extrage resursele, mapand coloanele dupa cuvinte-cheie (robust la reordonare):
  - C6 materiale: Nr | Denumire | U.M. | Consum | Pret unitar | Valoare | Furnizor
  - C7 manopera:  Nr | Meserie  | Consum (Om/ore) | Tarif mediu | Valoare | %
  - C8 utilaje:   Nr | Utilaj   | Ore de functionare | Tarif unitar | Valoare

`parse_extras(continut, ext) -> (tip, [dict])` unde dict = {cod, denumire, um,
cantitate, tarif_unitar, valoare, furnizor}. (None, []) daca nu e un extras C.
"""
from __future__ import annotations

from services.gantt.normalizare import normalizeaza
from services.gantt.modele import _to_float


def _detecteaza_tip(randuri) -> str | None:
    blob = ' '.join(normalizeaza(str(c)) for r in randuri[:6] for c in (r or []) if c)
    if 'formular c6' in blob or 'resurse materiale' in blob:
        return 'material'
    if 'formular c7' in blob or 'mana de lucru' in blob or 'meseriei' in blob:
        return 'manopera'
    if 'formular c8' in blob or 'ore de functionare' in blob or 'utilajelor' in blob:
        return 'utilaj'
    return None


def _mapeaza(antet: list, tip: str) -> dict:
    """{camp: index} din antet, dupa cuvinte-cheie."""
    h = [normalizeaza(str(c)) for c in antet]
    harta = {}
    for i, c in enumerate(h):
        if not c:
            continue
        if 'denumire' in c and 'denumire' not in harta:
            harta['denumire'] = i
        elif c in ('um', 'u m') or 'u.m' in c or c == 'unitate':
            harta['um'] = i
        elif ('consum' in c or 'ore' in c) and 'cantitate' not in harta:
            harta['cantitate'] = i
        elif ('pret' in c or 'tarif' in c) and 'tarif' not in harta:
            harta['tarif'] = i
        elif 'valoare' in c and 'valoare' not in harta:
            harta['valoare'] = i
        elif 'furnizor' in c:
            harta['furnizor'] = i
    return harta


def _gaseste_antet(randuri):
    """(index, harta) al randului-antet (contine 'denumire')."""
    for i, r in enumerate(randuri[:8]):
        h = [normalizeaza(str(c)) for c in (r or [])]
        if any('denumire' in c for c in h):
            return i
    return None


def _split_cod(text: str):
    """'100014449 - Surub fixare...' -> ('100014449', 'Surub fixare...')."""
    s = str(text or '').strip()
    if ' - ' in s:
        cod, den = s.split(' - ', 1)
        cod = cod.strip()
        if len(cod) <= 24:
            return cod, den.strip()
    return '', s


def parse_extras(continut: bytes, ext: str):
    """Intoarce (tip, [resurse]) sau (None, [])."""
    from services.gantt import import_engine
    try:
        sheets = import_engine._citeste_sheeturi(continut, ext)
    except Exception:
        return None, []
    if not sheets:
        return None, []
    _nume, randuri = sheets[0]
    tip = _detecteaza_tip(randuri)
    if not tip:
        return None, []

    idx = _gaseste_antet(randuri)
    if idx is None:
        return None, []
    harta = _mapeaza(randuri[idx], tip)
    if 'denumire' not in harta and tip != 'material':
        # C7/C8 uneori au denumirea pe col 1 fara eticheta clara -> fallback
        harta['denumire'] = 1

    def val(rand, camp, dflt=''):
        i = harta.get(camp)
        if i is None or i >= len(rand) or rand[i] is None:
            return dflt
        return str(rand[i]).strip()

    out = []
    start = idx + 1
    # sare randul de numerotare "0 1 2 ..."
    if start < len(randuri) and import_engine._este_rand_numerotare(randuri[start]):
        start += 1
    for r in randuri[start:]:
        if not r or not any(c is not None and str(c).strip() for c in r):
            continue
        den_raw = val(r, 'denumire')
        dn = normalizeaza(den_raw)
        # randurile de totalizare (TOTAL, Ore Manopera, etc.) - le sarim
        prim = normalizeaza(str(r[0]) if r else '')
        if (not den_raw and 'total' in ' '.join(normalizeaza(str(c)) for c in r)) \
                or dn.startswith('total') or prim.startswith('total') \
                or prim.startswith('ore manopera'):
            continue
        if not den_raw:
            continue
        cod, den = _split_cod(den_raw)
        cant = _to_float(val(r, 'cantitate'))
        tarif = _to_float(val(r, 'tarif'))
        valoare = _to_float(val(r, 'valoare')) or round(cant * tarif, 2)
        if cant <= 0 and valoare <= 0:
            continue
        out.append({
            'cod': cod, 'denumire': den[:400],
            'um': (val(r, 'um') or ('ora' if tip != 'material' else '')) or None,
            'cantitate': cant, 'tarif_unitar': tarif, 'valoare': valoare,
            'furnizor': (val(r, 'furnizor') or None) if tip == 'material' else None,
        })
    return tip, out
