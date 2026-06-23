"""
Nivelare resurse (resource leveling) - vedere DERIVATA, nu se salveaza peste plan.

Problema: motorul CPM (program.py) calculeaza start/finish IGNORAND capacitatea de
resurse. In realitate, pe o categorie de lucrare (ex BETON) ai un numar finit de
echipe/zi. Daca prea multe activitati de aceeasi categorie se suprapun, cererea
depaseste capacitatea => suprasolicitare.

Solutie: algoritm serial SGS (Serial Schedule Generation Scheme). Amana activitatile
cand cererea pe categorie/zi ar depasi capacitatea, respectand dependentele deja
calculate de motor. Rezultatul = un nou start/finish per activitate (DELTA fata de
plan), plus histograma incarcare vs capacitate. NU modifica obiectele Activitate
originale si NU atinge planul salvat.

Model de cerere (simplu si defensabil): fiecare activitate consuma 1 unitate din
resursa categoriei sale, in fiecare zi lucratoare in care e activa. Capacitatea =
numarul de unitati (echipe) disponibile/zi pe categorie. Categoriile FARA capacitate
definita = nelimitate (nu se niveleaza) => cu zero capacitati setate, nivelarea
coincide cu CPM (zero miscare, zero regresie).

Pur Python, fara DB. Plafon 50k activitati (return clar peste plafon).
"""
from __future__ import annotations

from collections import deque

PLAFON_ACTIVITATI = 50000


def _cheie_categorie(a) -> str:
    """Categoria pe care se aplica capacitatea: categorie_lucrare (F2 canonic) cu
    fallback la categorie_tehnologica. Normalizat UPPER (ca in TarifCategorie)."""
    cat = getattr(a, 'categorie_lucrare', None) or getattr(a, 'categorie_tehnologica', None)
    return (cat or 'NECLASIFICAT').strip().upper()


def _ordine_topologica(activitati, by_id) -> list:
    """Ordine topologica (predecesorii inaintea succesorilor). Identica ca logica
    cu program._ordine_topologica - copiem doar ca sa nu introducem dependinte ciudate
    (functia de acolo e privata si specifica forward pass-ului)."""
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
    if len(ordine) < len(activitati):   # ciclu rezidual -> adauga restul (fallback)
        vazute = set(ordine)
        ordine += [a.id for a in activitati if a.id not in vazute]
    return ordine


def _start_minim_din_dependente(a, plan_start: dict, plan_finish: dict, durata: int) -> int:
    """Cel mai devreme start admis de dependente, folosind start/finish NIVELATE ale
    predecesorilor (program.py aplica exact aceeasi formula pe valorile CPM)."""
    start = 0
    for d in a.predecesori:
        if d.predecesor_id not in plan_start:
            continue
        lag = int(d.decalaj or 0)
        tip = (d.tip or 'FS').upper()
        ps = plan_start[d.predecesor_id]
        pf = plan_finish[d.predecesor_id]
        if tip == 'SS':
            cand = ps + lag
        elif tip == 'FF':
            cand = pf + lag - durata
        elif tip == 'SF':
            cand = ps + lag - durata
        else:                       # FS (implicit)
            cand = pf + lag
        start = max(start, cand)
    return max(0, int(start))


def niveleaza(activitati, capacitati: dict | None = None) -> dict:
    """Niveleaza resursele prin SGS serial. NU muta obiectele originale.

    `capacitati`: {CATEGORIE_UPPER: nr_unitati_pe_zi}. Categorie absenta sau <=0
        => nelimitata (nu se niveleaza pe ea).

    Intoarce dict:
      {
        'ok': bool,
        'motiv': str,                # gol cand ok
        'durata_nivelata': int,      # zile (max finish nivelat)
        'durata_cpm': int,           # zile (max finish original)
        'intarziere': int,           # durata_nivelata - durata_cpm (>=0)
        'nr_mutate': int,            # cate activitati si-au schimbat start-ul
        'deltas': [                  # doar activitatile mutate
            {'id','cheie','nume','categorie',
             'start_cpm','finish_cpm','start_nivelat','finish_nivelat','delta'} ...
        ],
        'plan': {id: {'start_zi','finish_zi'}},   # programul nivelat complet
      }
    Cu capacitati gol/None => plan identic cu CPM (deltas gol).
    """
    capacitati = {str(k).strip().upper(): int(v)
                  for k, v in (capacitati or {}).items() if _capac_valida(v)}
    acts = list(activitati or [])
    n = len(acts)
    if n == 0:
        return {'ok': True, 'motiv': '', 'durata_nivelata': 0, 'durata_cpm': 0,
                'intarziere': 0, 'nr_mutate': 0, 'deltas': [], 'plan': {}}
    if n > PLAFON_ACTIVITATI:
        return {'ok': False,
                'motiv': f'Plan prea mare pentru nivelare ({n} activitati, plafon '
                         f'{PLAFON_ACTIVITATI}).',
                'durata_nivelata': 0, 'durata_cpm': 0, 'intarziere': 0,
                'nr_mutate': 0, 'deltas': [], 'plan': {}}

    by_id = {a.id: a for a in acts}
    # CPM original (din motor) - pastram valorile ca referinta pentru DELTA
    cpm_start = {a.id: int(a.start_zi or 0) for a in acts}
    cpm_finish = {a.id: int(a.finish_zi or 0) for a in acts}
    durata_cpm = max(cpm_finish.values(), default=0)

    # Prioritate SGS: start CPM crescator, apoi marja crescatoare (critic intai),
    # apoi durata descrescatoare (cele mari intai). Stabil pe id ca tie-break final.
    ordine_topo = {aid: i for i, aid in enumerate(_ordine_topologica(acts, by_id))}

    def prioritate(a):
        return (cpm_start[a.id], int(getattr(a, 'marja', 0) or 0),
                -max(1, int(a.durata or 1)), ordine_topo.get(a.id, 0))

    coada = sorted(acts, key=prioritate)

    # Incarcarea per categorie limitata: {categorie: {zi: nr_unitati_ocupate}}
    incarcare: dict = {cat: {} for cat in capacitati}
    plan_start: dict = {}
    plan_finish: dict = {}

    # Procesam in ordine topologica garantata: SGS serial cere ca un succesor sa fie
    # plasat dupa predecesori. `coada` e sortata pe prioritate dar dependentele se
    # respecta prin start_minim; procesam totusi in ordine topologica pentru ca
    # plan_start/finish al predecesorilor sa existe cand ajungem la succesor.
    coada.sort(key=lambda a: (ordine_topo.get(a.id, 0), prioritate(a)))

    for a in coada:
        durata = max(1, int(a.durata or 1))
        start = _start_minim_din_dependente(a, plan_start, plan_finish, durata)
        cat = _cheie_categorie(a)
        cap = capacitati.get(cat)
        if cap:
            load = incarcare[cat]
            start = _prima_fereastra_libera(start, durata, load, cap)
            for z in range(start, start + durata):
                load[z] = load.get(z, 0) + 1
        plan_start[a.id] = start
        plan_finish[a.id] = start + durata

    durata_nivelata = max(plan_finish.values(), default=0)

    deltas = []
    for a in acts:
        sn = plan_start[a.id]
        sc = cpm_start[a.id]
        if sn != sc:
            deltas.append({
                'id': a.id,
                'cheie': getattr(a, 'cheie', '') or '',
                'nume': a.nume,
                'categorie': _cheie_categorie(a),
                'start_cpm': sc,
                'finish_cpm': cpm_finish[a.id],
                'start_nivelat': sn,
                'finish_nivelat': plan_finish[a.id],
                'delta': sn - sc,
            })
    deltas.sort(key=lambda d: -d['delta'])

    return {
        'ok': True,
        'motiv': '',
        'durata_nivelata': durata_nivelata,
        'durata_cpm': durata_cpm,
        'intarziere': max(0, durata_nivelata - durata_cpm),
        'nr_mutate': len(deltas),
        'deltas': deltas,
        'plan': {aid: {'start_zi': plan_start[aid], 'finish_zi': plan_finish[aid]}
                 for aid in plan_start},
    }


def _capac_valida(v) -> bool:
    try:
        return int(v) > 0
    except (TypeError, ValueError):
        return False


def _prima_fereastra_libera(start: int, durata: int, load: dict, cap: int) -> int:
    """Cel mai devreme zi >= start unde activitatea (durata zile) incape sub plafon.

    SGS: incercam start; daca o zi din interval e plina (load >= cap), sarim chiar
    dupa prima zi plina si reincercam. Termina garantat (zilele indepartate au load 0).
    """
    z = start
    while True:
        plina = None
        for i in range(z, z + durata):
            if load.get(i, 0) >= cap:
                plina = i
                break
        if plina is None:
            return z
        z = plina + 1


def histograma_incarcare(activitati, plan: dict | None = None,
                         capacitati: dict | None = None,
                         max_zile: int = 4000) -> dict:
    """Cerere pe categorie/zi vs capacitate, pentru graficul de incarcare.

    `plan` (optional): {id: {'start_zi','finish_zi'}} - cand e dat (ex planul nivelat),
        foloseste-l; altfel ia start_zi/finish_zi de pe activitati (planul CPM).
    `capacitati`: {CATEGORIE: nr}; categoriile fara capacitate apar cu capacitate None.

    Intoarce {'categorii': [{'categorie','capacitate','varf','serie':[nr/zi]}],
              'durata_zile': int}. Doar categoriile cu cel putin o activitate.
    """
    capacitati = {str(k).strip().upper(): int(v)
                  for k, v in (capacitati or {}).items() if _capac_valida(v)}
    acts = list(activitati or [])
    if not acts:
        return {'categorii': [], 'durata_zile': 0}

    def s_f(a):
        if plan and a.id in plan:
            p = plan[a.id]
            return int(p.get('start_zi', 0) or 0), int(p.get('finish_zi', 0) or 0)
        return int(getattr(a, 'start_zi', 0) or 0), int(getattr(a, 'finish_zi', 0) or 0)

    durata = 0
    for a in acts:
        _, f = s_f(a)
        durata = max(durata, f)
    durata = min(max(durata, 1), max_zile)

    pe_cat: dict = {}
    for a in acts:
        s, f = s_f(a)
        cat = _cheie_categorie(a)
        serie = pe_cat.setdefault(cat, [0] * durata)
        for z in range(max(0, s), min(f, durata)):
            serie[z] += 1

    out = []
    for cat, serie in pe_cat.items():
        out.append({
            'categorie': cat,
            'capacitate': capacitati.get(cat),     # None = nelimitat
            'varf': max(serie) if serie else 0,
            'serie': serie,
        })
    # categoriile cu plafon (si depasiri) intai, apoi dupa varf descrescator
    out.sort(key=lambda c: (c['capacitate'] is None,
                            -(c['varf'] - (c['capacitate'] or 0))
                            if c['capacitate'] else 0,
                            -c['varf']))
    return {'categorii': out, 'durata_zile': durata}
