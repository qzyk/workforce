"""
Planificare Gantt din OBIECTIV (F1): consolideaza toate listele F3 ale unui
obiectiv intr-un singur plan, cu drill-down natural F1 -> F2 -> F3 in WBS.

Maparea pe ierarhia WBS existenta (obiect -> tronson -> categorie -> activitate):
  - nivel "obiect"  = Obiectul F2  ("[001] Arhitectura")
  - nivel "tronson" = Lista F3     ("Arhitectura c2 Lucrari noi")
  - nivel "categorie" + activitati = clasificarea tehnologica existenta

Strategia: articolele consolidate se serializeaza intr-un CSV intern care trece
prin EXACT fluxul existent (import_engine -> MotorPlanificare -> rezultat.html
cu diagrama/resurse/exporturi/salvare ca plan). Zero modificari in pipeline.

Functii publice:
  - articole_obiectiv(obiectiv_id) -> (list[ArticolF3], raport)
  - csv_obiectiv(obiectiv_id) -> (bytes, raport)   # CSV intern pt pipeline
"""

from __future__ import annotations

import csv
import io

from models import Obiectiv
from services.gantt import import_engine


def articole_obiectiv(obiectiv_id: int):
    """Parseaza toate listele F3 (GanttPlan.continut) ale obiectivului si
    eticheteaza fiecare articol cu obiect=F2 si tronson=lista F3.

    Returns: (articole, raport) - raport per lista: nr articole sau eroarea.
    Listele care nu se pot parsa NU opresc planificarea (raportate ca erori)."""
    ob = Obiectiv.query.get(obiectiv_id)
    if ob is None:
        raise ValueError(f'Obiectiv {obiectiv_id} inexistent')

    articole = []
    raport = {'obiectiv': ob.nume, 'liste': [], 'erori': 0, 'nr_articole': 0}
    for o in ob.obiecte:
        eticheta_obiect = f'[{o.cod}] {o.nume}' if o.cod else o.nume
        for plan in o.planuri:
            intrare = {'obiect': eticheta_obiect, 'lista': plan.nume,
                       'fisier': plan.nume_fisier}
            if not plan.continut:
                intrare['eroare'] = 'continut gol'
                raport['erori'] += 1
                raport['liste'].append(intrare)
                continue
            try:
                arts, _rap = import_engine.importa(plan.continut, plan.ext or '.xls')
            except import_engine.EroareImport as e:
                intrare['eroare'] = str(e)[:120]
                raport['erori'] += 1
                raport['liste'].append(intrare)
                continue
            for a in arts:
                a.obiect = eticheta_obiect
                a.tronson = plan.nume or '(lista)'
            articole.extend(arts)
            intrare['nr_articole'] = len(arts)
            raport['liste'].append(intrare)
    raport['nr_articole'] = len(articole)
    return articole, raport


# Antetul CSV-ului intern - sinonime recunoscute de import_engine
# (cod_articol/denumire/um/cantitate/obiect/tronson + coloanele pret_*).
_ANTET = ['cod_articol', 'denumire', 'um', 'cantitate', 'obiect', 'tronson',
          'pret unitar', 'pret material', 'pret manopera', 'pret utilaj', 'pret total']


def csv_obiectiv(obiectiv_id: int):
    """Serializeaza articolele consolidate intr-un CSV intern (bytes).

    CSV-ul trece prin fluxul existent de planificare (genereaza_din_fisier),
    deci planul obiectivului beneficiaza de tot: diagrama, resurse, exporturi,
    salvare ca GanttPlan. Returns: (csv_bytes, raport)."""
    articole, raport = articole_obiectiv(obiectiv_id)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';', quoting=csv.QUOTE_MINIMAL)
    w.writerow(_ANTET)
    for a in articole:
        w.writerow([
            a.cod_articol or '', a.denumire or '', a.um or '',
            _nr(a.cantitate), a.obiect or '', a.tronson or '',
            _nr(a.pret_unitar), _nr(a.pret_material), _nr(a.pret_manopera),
            _nr(a.pret_utilaj), _nr(a.pret_total),
        ])
    return buf.getvalue().encode('utf-8'), raport


def _nr(v) -> str:
    """Numar cu punct zecimal, fara separatori de mii (parsabil de _to_float)."""
    return f'{float(v or 0):.4f}'
