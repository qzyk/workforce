"""
Planificare automata a executiei (Faza 3) din elementele BIM.

Grupeaza elementele pe (faza tehnologica, nivel), calculeaza durata fiecarui
grup din norme de productivitate (randament/echipa/zi), le inlantuie in ordine
tehnologica (fundatii -> structura -> inchideri -> finisaje -> instalatii) pe
zile lucratoare (fara weekend + sarbatori legale) si creeaza cate un
BIMTaskSchedule per element (fereastra grupului) -> grafic 4D editabil.
"""

from __future__ import annotations

import datetime as _dt
import logging
import math

_logger = logging.getLogger(__name__)

# norme orientative 2026: (categorie, um, randament/echipa/zi, echipe_default)
NORME_2026 = [
    ('beton', 'mc', 25, 1),
    ('armatura', 'kg', 400, 1),
    ('cofraje', 'mp', 60, 1),
    ('confectii_metalice', 'kg', 800, 1),
    ('zidarie', 'mp', 25, 1),
    ('tencuiala', 'mp', 80, 1),
    ('finisaje', 'mp', 40, 1),
    ('diverse', 'buc', 20, 1),
]

# ordine tehnologica (rank mai mic = mai devreme)
FAZA_ORDINE = {
    'sapaturi': 1, 'fundatii': 2,
    'beton': 3, 'armatura': 3, 'cofraje': 3, 'confectii_metalice': 3,
    'zidarie': 4,
    'tencuiala': 5, 'finisaje': 5,
    'hvac': 6, 'sanitare': 6, 'electrice': 6,
    'diverse': 7,
}
DISCIPLINA_FAZA = {1: 'structural', 2: 'structural', 3: 'structural',
                   4: 'arhitectura', 5: 'arhitectura', 6: 'instalatii', 7: 'general'}


def seed_norme(tenant_id=None, commit=True):
    from models import db, NormaProductivitate
    adaugate = 0
    for cat, um, rand, echipe in NORME_2026:
        if NormaProductivitate.query.filter_by(tenant_id=tenant_id, categorie_lucrare=cat).first():
            continue
        db.session.add(NormaProductivitate(
            tenant_id=tenant_id, categorie_lucrare=cat, um=um,
            randament_zi=rand, echipe_default=echipe))
        adaugate += 1
    if commit and adaugate:
        db.session.commit()
    return adaugate


def _ensure_norme():
    from models import NormaProductivitate
    if NormaProductivitate.query.filter_by(tenant_id=None).count() == 0:
        seed_norme(tenant_id=None)


def _norme_dict():
    from models import NormaProductivitate
    _ensure_norme()
    return {n.categorie_lucrare: (float(n.randament_zi), n.echipe_default or 1)
            for n in NormaProductivitate.query.filter_by(tenant_id=None).all()}


def _este_lucratoare(d, sarbatori):
    return d.weekday() < 5 and d not in sarbatori


def _next_lucratoare(d, sarbatori):
    while not _este_lucratoare(d, sarbatori):
        d += _dt.timedelta(days=1)
    return d


def _adauga_zile_lucratoare(start, n, sarbatori):
    """start lucratoare; intoarce data dupa n zile lucratoare (n=0 -> start)."""
    d = start
    ramase = n
    while ramase > 0:
        d += _dt.timedelta(days=1)
        if _este_lucratoare(d, sarbatori):
            ramase -= 1
    return d


def genereaza_program(santier_id, data_start, user, echipe_factor=1):
    """
    Genereaza graficul de executie (BIMTaskSchedule per element) pentru santier.
    Idempotent: sterge schedule-urile auto anterioare. Returneaza rezumat.
    """
    from models import (db, Cladire, Nivel, ElementBIM, SarbatoareLegala,
                        BIMTaskSchedule)
    from services import pricing_bim, bim_4d

    _ensure_norme()
    cladiri_ids = [c.id for c in Cladire.query.filter_by(santier_id=santier_id).all()]
    if not cladiri_ids:
        return {'status': 'eroare', 'mesaj': 'Niciun element pe santier.'}
    elems = ElementBIM.query.filter(
        ElementBIM.cladire_id.in_(cladiri_ids),
        ElementBIM.cantitate.isnot(None)).all()
    if not elems:
        return {'status': 'eroare',
                'mesaj': 'Elementele nu au cantitate. Ruleaza intai calculul de cantitati.'}

    niveluri = {n.id: (n.ordine or 0)
                for n in Nivel.query.filter(Nivel.cladire_id.in_(cladiri_ids)).all()}
    norme = _norme_dict()

    grupuri = {}
    for el in elems:
        cat, _um = pricing_bim.categorie_si_um(el)
        rank = FAZA_ORDINE.get(cat, 7)
        key = (rank, cat, el.nivel_id)
        g = grupuri.setdefault(key, {'elems': [], 'cant': 0.0})
        g['elems'].append(el)
        g['cant'] += float(el.cantitate or 0)

    sarbatori = set()
    for s in SarbatoareLegala.query.all():
        d = getattr(s, 'data', None)
        if d:
            sarbatori.add(d)

    ids = [e.id for e in elems]
    BIMTaskSchedule.query.filter(
        BIMTaskSchedule.element_bim_id.in_(ids),
        BIMTaskSchedule.descriere == 'auto-planning').delete(synchronize_session=False)

    running = _next_lucratoare(data_start, sarbatori)
    data_final = running
    nr_tasks = 0
    for key in sorted(grupuri, key=lambda k: (k[0], niveluri.get(k[2], 0), k[1])):
        rank, cat, _nivel_id = key
        g = grupuri[key]
        rand, echipe = norme.get(cat, (10.0, 1))
        echipe = max(1, echipe * echipe_factor)
        durata = max(1, math.ceil(g['cant'] / (rand * echipe))) if g['cant'] else 1
        start = _next_lucratoare(running, sarbatori)
        finish = _adauga_zile_lucratoare(start, durata - 1, sarbatori)
        for el in g['elems']:
            bim_4d.create_schedule(
                el.id, faza=cat, data_start_plan=start, data_sfarsit_plan=finish,
                user=user, disciplina=DISCIPLINA_FAZA.get(rank),
                descriere='auto-planning', commit=False)
            nr_tasks += 1
        running = _adauga_zile_lucratoare(finish, 1, sarbatori)
        if finish > data_final:
            data_final = finish

    db.session.commit()
    return {
        'status': 'ok',
        'nr_taskuri': nr_tasks,
        'nr_grupuri': len(grupuri),
        'data_start': data_start.isoformat(),
        'data_final': data_final.isoformat(),
        'durata_zile_calendaristice': (data_final - data_start).days + 1,
    }
