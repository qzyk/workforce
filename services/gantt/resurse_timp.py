"""
Esalonarea resurselor in timp (resource-loaded schedule).

Din planul Gantt (start_zi/finish_zi + descompunere M/m/U pe activitate) produce:
  - histograma de cost pe perioade (luna SI saptamana): material / manopera / utilaj
  - cash-flow cumulat (curba S in bani)
  - manopera ore/perioada (estimat din valoare / tarif orar, cand nu sunt ore explicite)
  - varful de resurse (perioada cu cost maxim)

Distribuie costul fiecarei activitati uniform pe zilele ei lucratoare. Fara
dependente externe — se bazeaza doar pe rezultatul pipeline-ului.
"""
from __future__ import annotations

from datetime import date, timedelta

from .diagrama import _calendar_lucrator

TARIF_ORAR = 30.0   # lei/ora pt estimarea orelor de manopera din valoare


def _chei(d: date):
    """(cheie_luna, eticheta_luna, cheie_sapt, eticheta_sapt) pentru o data."""
    iso = d.isocalendar()
    luni = d - timedelta(days=d.weekday())
    return ((d.year, d.month), f'{d.month:02d}.{d.year}',
            (iso[0], iso[1]), f'S{iso[1]:02d} {luni.day:02d}.{luni.month:02d}')


def histograma_resurse(rezultat, data_start: date | None = None,
                       calendar=None) -> dict:
    """{'luna': [...], 'saptamana': [...], 'varf': {...}, 'bac': float}.
    `calendar` (optional): calendar de lucru real; None = doar Lu-Vi (istoric)."""
    activitati = [a for a in getattr(rezultat, 'activitati', []) if (a.valoare or 0) > 0]
    data_start = data_start or date.today()
    durata = 1
    for a in activitati:
        durata = max(durata, int(a.finish_zi or 0) + 1)
    cal = _calendar_lucrator(data_start, durata, calendar)

    def dz(i):
        return cal[max(0, min(int(i), len(cal) - 1))]

    luna: dict = {}
    sapt: dict = {}

    def buc(store, k, e, mat, man, uti):
        s = store.get(k)
        if s is None:
            s = store[k] = {'eticheta': e, 'material': 0.0, 'manopera': 0.0,
                            'utilaj': 0.0, 'total': 0.0}
        s['material'] += mat
        s['manopera'] += man
        s['utilaj'] += uti
        s['total'] += mat + man + uti

    for a in activitati:
        s0 = int(a.start_zi or 0)
        s1 = max(s0, int(a.finish_zi or s0))
        nd = s1 - s0 + 1
        mat = (a.valoare_material or 0) / nd
        man = (a.valoare_manopera or 0) / nd
        uti = (a.valoare_utilaj or 0) / nd
        # restul (daca valoarea totala > M+m+U) -> il atasam la material
        rest = ((a.valoare or 0) - (a.valoare_material or 0)
                - (a.valoare_manopera or 0) - (a.valoare_utilaj or 0)) / nd
        if rest > 0:
            mat += rest
        for zi in range(s0, s1 + 1):
            d = dz(zi)
            lk, le, sk, se = _chei(d)
            buc(luna, lk, le, mat, man, uti)
            buc(sapt, sk, se, mat, man, uti)

    def serie(store):
        out, cum = [], 0.0
        for k in sorted(store):
            s = store[k]
            cum += s['total']
            out.append({'eticheta': s['eticheta'],
                        'material': round(s['material'], 0),
                        'manopera': round(s['manopera'], 0),
                        'utilaj': round(s['utilaj'], 0),
                        'total': round(s['total'], 0),
                        'cumulat': round(cum, 0),
                        'ore_manopera': round((s['manopera'] / TARIF_ORAR), 0)})
        return out

    sl = serie(luna)
    varf = max(sl, key=lambda x: x['total']) if sl else None
    bac = round(sum(a.valoare or 0 for a in activitati), 0)
    return {'luna': sl, 'saptamana': serie(sapt), 'varf': varf, 'bac': bac,
            'durata_zile': durata}
