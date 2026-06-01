"""
Programare (forward pass CPM) + curba S de cost.

Calculeaza pentru fiecare activitate `start_zi`/`finish_zi` (index de zi 0-based,
intervalul [start, finish) acopera `durata` zile lucratoare) respectand tipul de
dependenta si decalajul:
    FS: succ.start >= pred.finish + lag
    SS: succ.start >= pred.start  + lag
    FF: succ.finish>= pred.finish + lag
    SF: succ.finish>= pred.start  + lag

Graful e un DAG (validare verifica ciclurile). Curba S distribuie costul fiecarei
activitati liniar pe durata ei -> cost cumulat in timp (pentru grafic / raport).
"""
from __future__ import annotations

from collections import deque


def _ordine_topologica(activitati, by_id):
    indeg = {a.id: 0 for a in activitati}
    succ = {a.id: [] for a in activitati}
    for a in activitati:
        for d in a.predecesori:
            if d.predecesor_id in by_id and d.predecesor_id != a.id:
                succ[d.predecesor_id].append(a.id)
                indeg[a.id] += 1
    coada = deque(i for i, g in indeg.items() if g == 0)
    ordine = []
    while coada:
        x = coada.popleft()
        ordine.append(x)
        for s in succ[x]:
            indeg[s] -= 1
            if indeg[s] == 0:
                coada.append(s)
    if len(ordine) < len(activitati):  # ciclu rezidual -> adauga restul (fallback)
        vazute = set(ordine)
        ordine += [a.id for a in activitati if a.id not in vazute]
    return ordine


def programeaza(activitati) -> int:
    """Forward pass: seteaza start_zi/finish_zi pe activitati. Intoarce durata totala (zile)."""
    if not activitati:
        return 0
    by_id = {a.id: a for a in activitati}
    for aid in _ordine_topologica(activitati, by_id):
        a = by_id[aid]
        durata = max(1, int(a.durata or 1))
        start = 0
        for d in a.predecesori:
            p = by_id.get(d.predecesor_id)
            if not p:
                continue
            lag = int(d.decalaj or 0)
            tip = (d.tip or 'FS').upper()
            if tip == 'SS':
                cand = p.start_zi + lag
            elif tip == 'FF':
                cand = p.finish_zi + lag - durata
            elif tip == 'SF':
                cand = p.start_zi + lag - durata
            else:  # FS (implicit)
                cand = p.finish_zi + lag
            start = max(start, cand)
        a.start_zi = max(0, int(start))
        a.finish_zi = a.start_zi + durata
    return max((a.finish_zi for a in activitati), default=0)


def curba_s(activitati, durata_totala: int, max_puncte: int = 120) -> list:
    """Cost cumulat pe zi (esantionat la max_puncte). [{zi, cumulat, procent}]."""
    if durata_totala <= 0:
        return []
    pe_zi = [0.0] * durata_totala
    for a in activitati:
        dz = max(1, a.finish_zi - a.start_zi)
        cota = (a.valoare or 0) / dz
        for z in range(a.start_zi, min(a.finish_zi, durata_totala)):
            pe_zi[z] += cota
    cumul = []
    c = 0.0
    for v in pe_zi:
        c += v
        cumul.append(c)
    total = cumul[-1] or 1.0

    if durata_totala <= max_puncte:
        idxs = range(durata_totala)
    else:
        step = durata_totala / max_puncte
        idxs = sorted({int((i + 1) * step) - 1 for i in range(max_puncte)} | {durata_totala - 1})
    return [{'zi': z + 1, 'cumulat': round(cumul[z], 2),
             'procent': round(100 * cumul[z] / total, 1)} for z in idxs]
