"""
Motor de validare a structurii de planificare (validare de graf).

Detecteaza:
  - ID-uri duplicate
  - predecesori inexistenti (referinte rupte)
  - tipuri de relatie invalide (alta valoare decat FS/SS/FF/SF)
  - activitati neclasificate
  - activitati orfane (fara predecesor si fara succesor)
  - cicluri (dependente circulare) -> ar bloca calculul de drum critic

Implementare PUR PYTHON (DFS pentru cicluri, grade pentru orfani). Daca networkx e
instalat, il foloseste pentru detectia ciclurilor (mai robusta), altfel fallback intern.
"""
from __future__ import annotations

from .modele import Activitate, Problema, RaportValidare, TIPURI_RELATIE

try:
    import networkx as nx  # optional
    _ARE_NX = True
except Exception:  # pragma: no cover
    _ARE_NX = False


def valideaza(activitati) -> RaportValidare:
    probleme: list = []
    ids = [a.id for a in activitati]
    set_ids = set(ids)

    # 1. ID-uri duplicate
    vazute = set()
    for i in ids:
        if i in vazute:
            probleme.append(Problema('id_duplicat', f'ID activitate duplicat: {i}', 'eroare'))
        vazute.add(i)

    # 2. predecesori + tipuri + construire adiacenta (pred -> succ)
    adiacenta: dict = {a.id: [] for a in activitati}
    grad_intern: dict = {a.id: 0 for a in activitati}
    for a in activitati:
        for d in a.predecesori:
            if d.tip not in TIPURI_RELATIE:
                probleme.append(Problema(
                    'tip_invalid', f'{a.id}: tip relatie invalid "{d.tip}"', 'eroare'))
            if d.predecesor_id not in set_ids:
                probleme.append(Problema(
                    'predecesor_lipsa',
                    f'{a.id}: predecesor inexistent "{d.predecesor_id}"', 'eroare'))
            else:
                adiacenta[d.predecesor_id].append(a.id)
                grad_intern[a.id] += 1

    # 3. activitati neclasificate
    for a in activitati:
        if not a.categorie_tehnologica:
            probleme.append(Problema(
                'neclasificat', f'{a.id} ({a.cod}): activitate neclasificata', 'avertisment'))

    # 4. orfani (fara predecesor si fara succesor) - normal pentru proiecte mici, info
    are_succesor = {k for k, v in adiacenta.items() if v}
    for a in activitati:
        if grad_intern.get(a.id, 0) == 0 and a.id not in are_succesor:
            probleme.append(Problema(
                'orfan', f'{a.id} ({a.cod}): fara predecesor si fara succesor', 'info'))

    # 5. cicluri
    for ciclu in _detecteaza_cicluri(adiacenta):
        probleme.append(Problema(
            'ciclu', 'Dependenta circulara: ' + ' -> '.join(ciclu), 'eroare'))

    return RaportValidare(probleme=probleme, nr_activitati=len(activitati))


def _detecteaza_cicluri(adiacenta: dict, limita: int = 50) -> list:
    """Intoarce o lista de cicluri (fiecare ca lista de id-uri). Limiteaza nr. raportat."""
    if _ARE_NX:
        g = nx.DiGraph()
        for u, vecini in adiacenta.items():
            g.add_node(u)
            for v in vecini:
                g.add_edge(u, v)
        cicluri = []
        try:
            for c in nx.simple_cycles(g):
                cicluri.append(list(c) + [c[0]])
                if len(cicluri) >= limita:
                    break
        except Exception:
            pass
        return cicluri
    return _cicluri_dfs(adiacenta, limita)


def _cicluri_dfs(adiacenta: dict, limita: int) -> list:
    """DFS cu 3 culori (alb/gri/negru) pentru detectia ciclurilor. Iterativ (fara recursie)
    ca sa nu dam stack overflow pe 100k noduri."""
    ALB, GRI, NEGRU = 0, 1, 2
    culoare = {n: ALB for n in adiacenta}
    cicluri = []
    for start in adiacenta:
        if culoare[start] != ALB:
            continue
        # stiva de (nod, iterator copii); stiva_cale = drumul curent
        stiva = [(start, iter(adiacenta[start]))]
        cale = [start]
        culoare[start] = GRI
        in_cale = {start}
        while stiva:
            nod, it = stiva[-1]
            avansat = False
            for urm in it:
                if culoare.get(urm, NEGRU) == GRI and urm in in_cale:
                    # ciclu gasit: portiunea din cale de la urm pana la nod
                    idx = cale.index(urm)
                    cicluri.append(cale[idx:] + [urm])
                    if len(cicluri) >= limita:
                        return cicluri
                elif culoare.get(urm, NEGRU) == ALB:
                    culoare[urm] = GRI
                    stiva.append((urm, iter(adiacenta[urm])))
                    cale.append(urm)
                    in_cale.add(urm)
                    avansat = True
                    break
            if not avansat:
                culoare[nod] = NEGRU
                stiva.pop()
                if cale and cale[-1] == nod:
                    cale.pop()
                    in_cale.discard(nod)
    return cicluri
