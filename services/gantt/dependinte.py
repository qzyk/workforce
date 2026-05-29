"""
Motor de dependente tehnologice.

Pentru fiecare grup (obiect, tronson) - adica fiecare tronson/strada in parte:
  - INTRA-categorie: activitatile aceleiasi categorii se inlantuie secvential (FS 0),
    formand un bloc de lucru continuu (configurabil: 'secvential' | 'paralel').
  - INTER-categorie: pentru fiecare relatie din template (config dependinte.json),
    daca ambele categorii exista in tronson, se creeaza o legatura intre reprezentantii lor.

Astfel lantul tehnologic (TRASARE -> SAPATURA -> POZARE -> ... -> REFACERE) este REPLICAT
automat pentru fiecare tronson (template multiplication), fara legare manuala.

Alegerea reprezentantilor in functie de tipul relatiei:
  FS (Finish->Start): pred = ultima activitate din cat. A,  succ = prima din cat. B
  SS (Start->Start):  pred = prima din A,   succ = prima din B
  FF (Finish->Finish):pred = ultima din A,  succ = ultima din B
  SF (Start->Finish): pred = prima din A,   succ = ultima din B

Complexitate O(activitati + relatii*tronsoane) -> scaleaza la 100k+ activitati.
"""
from __future__ import annotations

from .modele import Activitate, Dependenta


def _reprezentanti(acts_pred, acts_succ, tip: str):
    """Intoarce (activitate_predecesoare, activitate_succesoare) pentru tipul de relatie."""
    pred = acts_pred[-1] if tip in ('FS', 'FF') else acts_pred[0]
    succ = acts_succ[0] if tip in ('FS', 'SS') else acts_succ[-1]
    return pred, succ


def genereaza_dependinte(activitati, relatii, intra_categorie: str = 'secvential',
                         ordine_categorii=None) -> int:
    """Genereaza predecesorii (muta activitatile pe loc). Intoarce nr. de dependente create.

    Doua faze pe fiecare tronson:
      1. relatii EXPLICITE din config (branch-uri + tip/decalaj specifice);
      2. CONECTIVITATE: daca o categorie prezenta (in ordinea tehnologica) nu a primit
         niciun predecesor inter-categorie (ex: o categorie intermediara lipseste din deviz),
         se leaga de cea precedenta categorie prezenta -> lantul ramane CONTINUU.
    """
    ordine = ordine_categorii or []
    # index pentru tip/decalaj specific pe perechea (from, to)
    rel_idx = {(r.get('from'), r.get('to')):
               (str(r.get('tip', 'FS')).upper(), int(r.get('decalaj', 0) or 0))
               for r in relatii}

    grupuri: dict = {}
    for a in activitati:
        g = grupuri.setdefault((a.obiect, a.tronson), {})
        g.setdefault(a.categorie_tehnologica, []).append(a)

    nr = 0
    for per_cat in grupuri.values():
        # INTRA-categorie (bloc de lucru continuu)
        if intra_categorie == 'secvential':
            for acts in per_cat.values():
                for i in range(1, len(acts)):
                    acts[i].predecesori.append(Dependenta(acts[i - 1].id, 'FS', 0))
                    nr += 1

        primite_inter = set()  # categorii care au primit deja un predecesor inter-categorie

        # FAZA 1 - relatii explicite din template
        for rel in relatii:
            ca, cb = rel.get('from'), rel.get('to')
            tip = str(rel.get('tip', 'FS')).upper()
            lag = int(rel.get('decalaj', 0) or 0)
            if ca in per_cat and cb in per_cat and ca != cb:
                pred, succ = _reprezentanti(per_cat[ca], per_cat[cb], tip)
                if pred.id != succ.id:
                    succ.predecesori.append(Dependenta(pred.id, tip, lag))
                    nr += 1
                    primite_inter.add(cb)

        # FAZA 2 - conectivitate pe categoriile prezente, in ordinea tehnologica
        prezente = [c for c in ordine if c in per_cat]
        for i in range(1, len(prezente)):
            cb = prezente[i]
            if cb in primite_inter:
                continue
            ca = prezente[i - 1]
            tip, lag = rel_idx.get((ca, cb), ('FS', 0))
            pred, succ = _reprezentanti(per_cat[ca], per_cat[cb], tip)
            if pred.id != succ.id:
                succ.predecesori.append(Dependenta(pred.id, tip, lag))
                nr += 1
                primite_inter.add(cb)
    return nr
