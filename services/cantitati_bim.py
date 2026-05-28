"""
Extragere cantitati pentru ElementBIM din IFC (Faza 1 auto-pricing/planning).

Per element, in ordine:
  1. Qto din IFC (IfcElementQuantity) daca exista - rapid.
  2. Fallback geometric (ifcopenshell.geom + util.shape) - volum/arie/greutate.

Deschide fisierul IFC al modelului si potriveste elementele dupa GlobalId cu
randurile ElementBIM. Geometria e LENTA (~9 ms/elem) -> pentru modele mari
ruleaza offline cu scripts/calcul_cantitati.py (evita timeout-ul web).
"""

from __future__ import annotations

import logging
import os
from decimal import Decimal

_logger = logging.getLogger(__name__)

DENSITATE_OTEL = 7850.0  # kg/mc - pentru armaturi / profile metalice

# tip_element -> unitate preferata
UM_GREUTATE = {'reinforcingbar', 'reinforcingmesh', 'tendon', 'rebar'}
UM_LUNGIME = {'pipe', 'duct', 'cablecarriersegment', 'cable_tray',
              'pipesegment', 'ductsegment', 'railing'}


def _qto_flat(inst):
    try:
        import ifcopenshell.util.element as ue
        psets = ue.get_psets(inst, qtos_only=True)
    except Exception:
        return {}
    flat = {}
    for s in psets.values():
        for k, v in s.items():
            if isinstance(v, (int, float)):
                flat[k] = float(v)
    return flat


def _din_qto(inst, tip):
    q = _qto_flat(inst)
    if not q:
        return None, None
    lower = {k.lower(): v for k, v in q.items()}

    def pick(*keys):
        for k in keys:
            if lower.get(k.lower()):
                return lower[k.lower()]
        return None

    if tip in UM_GREUTATE:
        w = pick('NetWeight', 'GrossWeight', 'Weight')
        if w:
            return w, 'kg'
    if tip in UM_LUNGIME:
        ln = pick('Length')
        if ln:
            return ln, 'm'
    v = pick('NetVolume', 'GrossVolume', 'Volume')
    if v:
        return v, 'mc'
    a = pick('NetArea', 'GrossArea', 'NetSideArea', 'GrossSideArea', 'Area')
    if a:
        return a, 'mp'
    return None, None


def extrage_cantitati(model_id, doar_lipsa=True, max_elemente=None):
    """
    Extrage cantitatile elementelor modelului <model_id> (potrivire pe GlobalId).

    Args:
        doar_lipsa: proceseaza doar elementele fara cantitate.
        max_elemente: limita (pentru rulari partiale / teste).
    Returns: dict {status, mesaj, stats}.
    """
    from flask import current_app
    from models import db, ModelBIM, ElementBIM

    model = ModelBIM.query.get(model_id)
    if not model or not model.fisier_path:
        return {'status': 'eroare', 'mesaj': 'Model inexistent sau fara fisier IFC.', 'stats': {}}
    path = os.path.join(current_app.root_path, model.fisier_path)
    if not os.path.exists(path):
        return {'status': 'eroare', 'mesaj': f'Fisier IFC lipsa: {path}', 'stats': {}}

    try:
        import ifcopenshell
        import ifcopenshell.geom
        import ifcopenshell.util.shape as ush
    except ImportError:
        return {'status': 'eroare', 'mesaj': 'ifcopenshell nu e instalat.', 'stats': {}}

    try:
        ifc = ifcopenshell.open(path)
    except Exception as e:
        return {'status': 'eroare', 'mesaj': f'Nu pot deschide IFC: {e}', 'stats': {}}

    elems = {e.ifc_global_id: e for e in
             ElementBIM.query.filter(ElementBIM.ifc_global_id.isnot(None)).all()}
    settings = ifcopenshell.geom.settings()
    stats = {'din_qto': 0, 'din_geom': 0, 'fara': 0, 'procesate': 0}

    for inst in ifc.by_type('IfcElement'):
        if inst.is_a('IfcFeatureElement'):
            continue
        el = elems.get(getattr(inst, 'GlobalId', None))
        if el is None:
            continue
        if doar_lipsa and el.cantitate is not None:
            continue

        tip = (el.tip_element or '').lower()
        cant, um = _din_qto(inst, tip)
        sursa = 'qto'
        if cant is None:
            # fallback geometric
            try:
                shape = ifcopenshell.geom.create_shape(settings, inst)
                g = shape.geometry
                vol = ush.get_volume(g)
                if tip in UM_GREUTATE and vol and vol > 0:
                    cant, um = round(vol * DENSITATE_OTEL, 1), 'kg'
                elif vol and vol > 0:
                    cant, um = round(vol, 3), 'mc'
                else:
                    a = ush.get_area(g)
                    if a and a > 0:
                        cant, um = round(a, 3), 'mp'
                sursa = 'geom'
            except Exception as e:
                _logger.debug('geom esuat pentru %s: %s', getattr(inst, 'GlobalId', '?'), e)

        if cant is not None:
            el.cantitate = Decimal(str(cant))
            el.unitate_masura = um
            stats['din_qto' if sursa == 'qto' else 'din_geom'] += 1
        else:
            stats['fara'] += 1
        stats['procesate'] += 1
        if max_elemente and stats['procesate'] >= max_elemente:
            break

    db.session.commit()
    return {
        'status': 'ok',
        'mesaj': (f"Cantitati extrase: {stats['din_qto']} din Qto, "
                  f"{stats['din_geom']} geometric, {stats['fara']} fara."),
        'stats': stats,
    }
