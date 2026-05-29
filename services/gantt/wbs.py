"""
Motor WBS - genereaza ierarhia:

    Obiect
     └── Tronson
          └── Categorie tehnologica
               └── Activitate

Atribuie wbs_id (1.1.2.3), nivel (1..4) si relatii parinte-copil.
Categoriile sunt ordonate dupa ordinea tehnologica din config (nu alfabetic).
"""
from __future__ import annotations

from .modele import Activitate, NodWBS


# Nume "frumoase" pentru categoriile tehnologice (apar in WBS / export)
NUME_CATEGORIE = {
    'TRASARE': 'Trasari si pichetaj',
    'SAPATURA': 'Sapaturi',
    'SPRIJINIRI': 'Sprijiniri si epuismente',
    'POZARE_CONDUCTA': 'Pozare conducta',
    'CAMINE': 'Camine',
    'UMPLUTURA': 'Umpluturi si compactari',
    'REFACERE': 'Refaceri',
    'PROBE': 'Probe si receptii',
}


def _nume_categorie(cat) -> str:
    if not cat:
        return 'Neclasificate'
    return NUME_CATEGORIE.get(cat, cat.replace('_', ' ').title())


def _grupeaza(activitati, cheie):
    """Grupare stabila pastrand ordinea de prima aparitie. Intoarce dict {cheie: [activitati]}."""
    grupuri: dict = {}
    for a in activitati:
        grupuri.setdefault(cheie(a), []).append(a)
    return grupuri


def genereaza_wbs(activitati, ordine_categorii) -> list:
    """Construieste arborele WBS si seteaza wbs_id/nivel pe fiecare activitate.

    Returns: list[NodWBS] in ordine de parcurgere (preorder) - gata de export.
    """
    rang = {c: i for i, c in enumerate(ordine_categorii)}
    noduri: list = []

    obiecte = _grupeaza(activitati, lambda a: a.obiect or '(fara obiect)')
    for io, obi in enumerate(sorted(obiecte.keys(), key=_cheie_naturala), start=1):
        wbs_o = str(io)
        noduri.append(NodWBS(wbs_o, obi, 1, None, 'obiect'))

        tronsoane = _grupeaza(obiecte[obi], lambda a: a.tronson or '(fara tronson)')
        for it, tr in enumerate(sorted(tronsoane.keys(), key=_cheie_naturala), start=1):
            wbs_t = f'{wbs_o}.{it}'
            noduri.append(NodWBS(wbs_t, tr, 2, wbs_o, 'tronson'))

            categorii = _grupeaza(tronsoane[tr], lambda a: a.categorie_tehnologica or 'NECLASIFICAT')
            chei_cat = sorted(categorii.keys(), key=lambda c: (rang.get(c, 999), str(c)))
            for ic, cat in enumerate(chei_cat, start=1):
                wbs_c = f'{wbs_t}.{ic}'
                noduri.append(NodWBS(wbs_c, _nume_categorie(None if cat == 'NECLASIFICAT' else cat),
                                     3, wbs_t, 'categorie'))
                for ia, act in enumerate(categorii[cat], start=1):
                    act.wbs_id = f'{wbs_c}.{ia}'
                    act.nivel = 4
                    noduri.append(NodWBS(act.wbs_id, act.nume, 4, wbs_c, 'activitate', act.id))
    return noduri


def _cheie_naturala(s: str):
    """Sortare 'naturala' ca Strada 2 < Strada 10. Imparte in fragmente text/numar."""
    import re
    return [int(x) if x.isdigit() else x.lower()
            for x in re.split(r'(\d+)', str(s))]
