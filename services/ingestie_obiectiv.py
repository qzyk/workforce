"""
Ingestie obiectiv: construieste arborele Obiectiv (F1) -> Obiect (F2) -> GanttPlan (F3)
dintr-un folder de devize. Strict aditiv, idempotent.

`construieste_arbore(date, ...)` ia DATE deja parsate (dict) si scrie in DB -
testabil fara fisiere. `ingereaza(director, ...)` citeste folderul, parseaza
(reuse parsere F1/F2 + total F3 din B1) si cheama construieste_arbore.

Costul fiecarui plan F3 (cost_total) e luat din extractorul de total (B1).
Bytes-ul F3 e stocat in GanttPlan.continut pt pipeline-ul Gantt existent.
"""

from __future__ import annotations

import os
import re
from decimal import Decimal
from typing import Optional

from models import db, Obiectiv, Obiect, GanttPlan
from services.parsers import centralizator_f1f2 as cf
from services.reconciliere_obiectiv import clasifica_fisiere
from services.deviz_pricing import deduce_disciplina


# ============================================================
# Construire arbore in DB (din date parsate) - idempotent
# ============================================================

def construieste_arbore(date: dict, *, proiect_id: Optional[int] = None,
                        tenant_id: Optional[int] = None, creat_de_id: Optional[int] = None,
                        commit: bool = True) -> dict:
    """Creeaza/actualizeaza Obiectiv + Obiecte + GanttPlan-uri din `date`.

    `date` = {nume, cod?, nume_fisier_f1?, valoare_constructii?, valoare_totala?,
              valoare_cm?, obiecte: [{cod, nume, disciplina?, valoare_f2?, valoare_f1?,
              nume_fisier_f2?, planuri: [{nume, nume_fisier?, ext?, continut?, cost_total?}]}]}.
    Idempotent: Obiectiv pe (proiect_id, nume), Obiect pe (obiectiv, cod),
    GanttPlan pe (obiect, nume_fisier)."""
    # --- Obiectiv (upsert) ---
    ob = Obiectiv.query.filter_by(proiect_id=proiect_id, nume=date['nume'],
                                  tenant_id=tenant_id).first()
    if ob is None:
        ob = Obiectiv(tenant_id=tenant_id, proiect_id=proiect_id, nume=date['nume'],
                      cod=date.get('cod'), creat_de_id=creat_de_id)
        db.session.add(ob)
        db.session.flush()
    ob.valoare_constructii = date.get('valoare_constructii')
    ob.valoare_totala = date.get('valoare_totala')
    ob.valoare_cm = date.get('valoare_cm')
    ob.nume_fisier_f1 = date.get('nume_fisier_f1')

    stats = dict(obiectiv_id=ob.id, obiecte_create=0, obiecte_actualizate=0,
                 planuri_create=0, planuri_actualizate=0)

    for i, od in enumerate(date.get('obiecte', [])):
        obj = Obiect.query.filter_by(obiectiv_id=ob.id, cod=od.get('cod')).first()
        if obj is None:
            obj = Obiect(tenant_id=tenant_id, obiectiv_id=ob.id, cod=od.get('cod'),
                         nume=od['nume'], ordine=i)
            db.session.add(obj)
            db.session.flush()
            stats['obiecte_create'] += 1
        else:
            stats['obiecte_actualizate'] += 1
        obj.nume = od['nume']
        obj.disciplina = od.get('disciplina')
        obj.valoare_f2 = od.get('valoare_f2')
        obj.valoare_f1 = od.get('valoare_f1')
        obj.nume_fisier_f2 = od.get('nume_fisier_f2')
        obj.ordine = i

        for pd in od.get('planuri', []):
            plan = None
            if pd.get('nume_fisier'):
                plan = GanttPlan.query.filter_by(obiect_id=obj.id,
                                                 nume_fisier=pd['nume_fisier']).first()
            if plan is None:
                plan = GanttPlan(
                    tenant_id=tenant_id, proiect_id=proiect_id, obiect_id=obj.id,
                    nume=pd['nume'], nume_fisier=pd.get('nume_fisier'),
                    ext=pd.get('ext'), continut=pd.get('continut') or b'',
                    creat_de_id=creat_de_id,
                )
                db.session.add(plan)
                stats['planuri_create'] += 1
            else:
                stats['planuri_actualizate'] += 1
                plan.nume = pd['nume']
                plan.obiect_id = obj.id
                if pd.get('continut'):
                    plan.continut = pd['continut']
            plan.cost_total = pd.get('cost_total') or Decimal('0')

    if commit:
        db.session.commit()
    return stats


# ============================================================
# Citire folder -> date parsate
# ============================================================

_RE_CURATA = re.compile(r'(_?F3.*$|_lista_cantitati.*$)', re.IGNORECASE)


def _nume_plan(nume_fisier: str) -> str:
    """Nume lizibil de plan din numele fisierului F3."""
    baza = os.path.splitext(nume_fisier)[0]
    baza = _RE_CURATA.sub('', baza)
    baza = re.sub(r'^\d{3}[_\- ]\d{3}[_\- ]', '', baza)   # scoate prefixul cod
    return baza.replace('_', ' ').strip() or nume_fisier


def colecteaza_date(director: str, nume_obiectiv: Optional[str] = None) -> dict:
    """Parseaza folderul si intoarce structura `date` pentru construieste_arbore."""
    fisiere = clasifica_fisiere(director)
    f1p, f2map, f3map = fisiere['f1'], fisiere['f2'], fisiere['f3']

    f1 = cf.parse_f1_file(f1p) if f1p else {}
    # prima aparitie a fiecarui cod in F1 = linia de Constructii (4.1)
    obiecte_f1: dict[str, dict] = {}
    for o in f1.get('obiecte', []):
        obiecte_f1.setdefault(o['cod'], o)

    date = dict(
        nume=nume_obiectiv or os.path.basename(director.rstrip('/')) or 'Obiectiv',
        nume_fisier_f1=os.path.basename(f1p) if f1p else None,
        valoare_constructii=f1.get('total_4_1'),
        valoare_totala=f1.get('total'),
        obiecte=[],
    )

    # codurile de obiect = cheile F2 (plus orice cod din F1 fara F2)
    coduri = sorted(set(f2map) | set(obiecte_f1))
    for cod in coduri:
        f2 = cf.parse_f2_file(f2map[cod]) if cod in f2map else {'sub_obiecte': [], 'total': None}
        nume_obj = (obiecte_f1.get(cod, {}).get('nume')
                    or _nume_din_f2(f2map.get(cod, '')) or f'Obiect {cod}')
        planuri = []
        for (ob, sub), path in sorted(f3map.items()):
            if ob != cod:
                continue
            total, _n = cf.total_f3_file(path)
            with open(path, 'rb') as fh:
                continut = fh.read()
            nf = os.path.basename(path)
            planuri.append(dict(
                nume=_nume_plan(nf), nume_fisier=nf,
                ext=os.path.splitext(nf)[1], continut=continut, cost_total=total,
            ))
        date['obiecte'].append(dict(
            cod=cod, nume=nume_obj, disciplina=deduce_disciplina(nume_obj),
            valoare_f2=f2.get('total'),
            valoare_f1=obiecte_f1.get(cod, {}).get('valoare'),
            nume_fisier_f2=os.path.basename(f2map[cod]) if cod in f2map else None,
            planuri=planuri,
        ))
    return date


def _nume_din_f2(path: str) -> str:
    if not path:
        return ''
    baza = os.path.splitext(os.path.basename(path))[0]
    baza = re.sub(r'^\d{3}[_\- ]', '', baza)
    baza = re.sub(r'_?F2.*$', '', baza, flags=re.IGNORECASE)
    return baza.replace('_', ' ').strip()


def ingereaza(director: str, nume_obiectiv: Optional[str] = None, *,
              proiect_id: Optional[int] = None, tenant_id: Optional[int] = None,
              creat_de_id: Optional[int] = None, commit: bool = True) -> dict:
    """Citeste folderul obiectivului si construieste arborele in DB. Idempotent."""
    date = colecteaza_date(director, nume_obiectiv)
    stats = construieste_arbore(date, proiect_id=proiect_id, tenant_id=tenant_id,
                                creat_de_id=creat_de_id, commit=commit)
    stats['nume_obiectiv'] = date['nume']
    stats['nr_obiecte'] = len(date['obiecte'])
    stats['nr_planuri'] = sum(len(o['planuri']) for o in date['obiecte'])
    return stats
