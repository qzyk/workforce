"""
Strat de urmarire a executiei peste planul Gantt (Faza 2 tracking).

Functii PURE (fara Flask/DB) peste lista de Activitate deja programata:
- `snapshot_baseline(rezultat)` -> dict serializabil (plan de referinta inghetat)
- `compara_baseline(rezultat, baseline)` -> delta curent-vs-baseline pe cheia stabila
- `aplica_progres(activitati, progrese, data_stare, calendar)` -> progres pe bare +
  reprogramare retained-logic (durata ramasa = durata * (1 - pct/100))

Toate folosesc CHEIA STABILA a activitatii (`Activitate.cheie`), nu id-ul A000001,
deci sunt robuste la re-import (chei disparute / noi raportate, nu eroare).
"""
from __future__ import annotations

from datetime import date, timedelta


# ------------------------------------------------------------- BASELINE
def snapshot_baseline(rezultat) -> dict:
    """Construieste snapshot-ul de baseline dintr-un RezultatPlanificare programat.

    Structura: {'activitati': {cheie: {start_zi, finish_zi, durata, valoare, ...}},
                'curba_s': [...], 'meta': {bac, durata_zile, ...}}.
    Cheile fara `cheie` stabila (backward compat) sunt sarite.
    """
    st = rezultat.statistici or {}
    acts: dict = {}
    for a in (rezultat.activitati or []):
        ck = getattr(a, 'cheie', '') or ''
        if not ck:
            continue
        acts[ck] = {
            'id': a.id,
            'cod': a.cod,
            'nume': a.nume,
            'start_zi': int(a.start_zi or 0),
            'finish_zi': int(a.finish_zi or 0),
            'durata': int(a.durata or 0),
            'valoare': round(float(a.valoare or 0), 2),
            'critic': bool(a.critic),
        }
    return {
        'activitati': acts,
        'curba_s': st.get('curba_s', []),
        'meta': {
            'bac': round(float(st.get('cost_total', 0) or 0), 2),
            'durata_zile': int(st.get('durata_totala_zile', 0) or 0),
            'nr_activitati': int(st.get('nr_activitati', 0) or 0),
        },
    }


def compara_baseline(rezultat, baseline: dict) -> dict:
    """Comparatie curent (rezultat) vs baseline (dict din snapshot_baseline).

    Pe cheia stabila: pentru fiecare activitate comuna calculeaza delta de start /
    finish / durata / valoare. Cheile prezente doar intr-o parte sunt raportate
    separat (chei_disparute = in baseline dar nu in curent; chei_noi = invers) -
    NU se arunca eroare cand fisierul F3 s-a modificat intre timp.
    """
    base_acts = (baseline or {}).get('activitati', {}) or {}
    cur_by_cheie = {}
    for a in (rezultat.activitati or []):
        ck = getattr(a, 'cheie', '') or ''
        if ck:
            cur_by_cheie[ck] = a

    randuri = []
    for ck, b in base_acts.items():
        a = cur_by_cheie.get(ck)
        if a is None:
            continue   # disparuta -> raportata mai jos
        randuri.append({
            'cheie': ck,
            'cod': a.cod,
            'nume': a.nume,
            'baseline_start': int(b.get('start_zi', 0) or 0),
            'baseline_finish': int(b.get('finish_zi', 0) or 0),
            'baseline_durata': int(b.get('durata', 0) or 0),
            'baseline_valoare': round(float(b.get('valoare', 0) or 0), 2),
            'curent_start': int(a.start_zi or 0),
            'curent_finish': int(a.finish_zi or 0),
            'curent_durata': int(a.durata or 0),
            'curent_valoare': round(float(a.valoare or 0), 2),
            'delta_start': int(a.start_zi or 0) - int(b.get('start_zi', 0) or 0),
            'delta_finish': int(a.finish_zi or 0) - int(b.get('finish_zi', 0) or 0),
            'delta_durata': int(a.durata or 0) - int(b.get('durata', 0) or 0),
            'delta_valoare': round(float(a.valoare or 0) - float(b.get('valoare', 0) or 0), 2),
        })

    chei_baseline = set(base_acts.keys())
    chei_curent = set(cur_by_cheie.keys())
    chei_disparute = sorted(chei_baseline - chei_curent)
    chei_noi = sorted(chei_curent - chei_baseline)

    bmeta = (baseline or {}).get('meta', {}) or {}
    st = rezultat.statistici or {}
    randuri.sort(key=lambda r: -abs(r['delta_finish']))
    return {
        'randuri': randuri,
        'chei_disparute': chei_disparute,
        'chei_noi': chei_noi,
        'nr_disparute': len(chei_disparute),
        'nr_noi': len(chei_noi),
        'baseline_durata_zile': int(bmeta.get('durata_zile', 0) or 0),
        'curent_durata_zile': int(st.get('durata_totala_zile', 0) or 0),
        'delta_durata_zile': int(st.get('durata_totala_zile', 0) or 0)
                             - int(bmeta.get('durata_zile', 0) or 0),
        'baseline_bac': round(float(bmeta.get('bac', 0) or 0), 2),
        'curent_bac': round(float(st.get('cost_total', 0) or 0), 2),
        'delta_bac': round(float(st.get('cost_total', 0) or 0)
                           - float(bmeta.get('bac', 0) or 0), 2),
    }


# ------------------------------------------------------------- PROGRES
def _clamp_pct(v) -> float:
    try:
        p = float(v)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(100.0, p))


def aplica_progres(activitati, progrese: dict, data_stare: date = None,
                   calendar=None) -> dict:
    """Aplica progresul fizic peste activitatile programate (retained logic).

    `progrese`: dict {cheie_activitate: {'procent': float, 'data_start_real': date|None,
                'data_finish_real': date|None}}.
    `data_stare`: data de stare (status / data date). Daca None -> date.today().
    `calendar`: CalendarLucru optional (folosit la mapare zi->data); None = doar Lu-Vi.

    Efect (pur in-memory, NU atinge DB):
    - seteaza atribut tranzitoriu `progres_pct` pe fiecare Activitate (0..100);
    - durata ramasa = durata * (1 - pct/100); activitatile 100% sunt complet realizate;
    - intoarce un sumar agregat (% mediu ponderat pe valoare, EV, nr in curs/gata).

    NU re-aseaza start_zi/finish_zi ale altor activitati (reprogramarea CPM ramane
    pe Faza urmatoare); aici doar atasam progresul si calculam EV / durata ramasa.
    """
    acts = activitati or []
    progrese = progrese or {}
    if data_stare is None:
        data_stare = date.today()

    val_total = 0.0
    ev_total = 0.0          # earned value = suma(pct/100 * valoare)
    nr_in_curs = 0
    nr_gata = 0
    nr_cu_progres = 0
    for a in acts:
        ck = getattr(a, 'cheie', '') or ''
        info = progrese.get(ck) if ck else None
        pct = _clamp_pct(info.get('procent') if info else 0.0)
        # atribut tranzitoriu pe dataclass (nu e in __init__, dar dataclass-ul nu e frozen)
        a.progres_pct = pct
        durata = max(0, int(a.durata or 0))
        a.durata_ramasa = durata * (1.0 - pct / 100.0)
        val = float(a.valoare or 0)
        val_total += val
        ev_total += val * pct / 100.0
        if pct >= 100.0:
            nr_gata += 1
        elif pct > 0.0:
            nr_in_curs += 1
        if info:
            nr_cu_progres += 1

    procent_mediu = round(100.0 * ev_total / val_total, 2) if val_total > 0 else (
        round(sum(getattr(a, 'progres_pct', 0.0) for a in acts) / len(acts), 2) if acts else 0.0)
    return {
        'data_stare': data_stare.isoformat(),
        'nr_activitati': len(acts),
        'nr_cu_progres': nr_cu_progres,
        'nr_in_curs': nr_in_curs,
        'nr_gata': nr_gata,
        'procent_mediu': procent_mediu,
        'ev': round(ev_total, 2),
        'bac': round(val_total, 2),
    }


def progres_curent_din_jurnal(progrese_db) -> dict:
    """Reduce un jurnal append-only (list de GanttProgres) la progresul CURENT
    per cheie: ultima inregistrare dupa (data, data_creare). Intoarce
    {cheie: {'procent', 'data_start_real', 'data_finish_real', 'data'}}.
    """
    curent: dict = {}
    for p in progrese_db:
        ck = p.cheie_activitate
        prev = curent.get(ck)
        cheie_sort = (p.data, p.data_creare or p.data)
        if prev is None or cheie_sort >= prev['_sort']:
            curent[ck] = {
                '_sort': cheie_sort,
                'procent': float(p.procent_fizic or 0),
                'data_start_real': p.data_start_real,
                'data_finish_real': p.data_finish_real,
                'data': p.data,
            }
    for v in curent.values():
        v.pop('_sort', None)
    return curent
