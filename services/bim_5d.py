"""
5D Cost service: cost per element BIM cu agregare pe disciplina/fazа/cladire.

Capabilitati:
- create/update cost item
- agregare per element (total cost = sum cantitate*pret_unitar pe categorii)
- agregare per cladire / santier / disciplina / faza
- comparare planificat vs real
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import func

from models import db, BIMCostItem, ElementBIM, Cladire
from services import audit as audit_svc


_logger = logging.getLogger(__name__)


# ====================================================
# CRUD
# ====================================================

def create_cost_item(element_bim_id: int, descriere: str,
                     cantitate: float, pret_unitar: float,
                     *, user, categorie: str = 'material',
                     unitate: str = 'buc', faza: Optional[str] = None,
                     tip: str = 'planificat', valuta: str = 'RON',
                     referinta_extern: Optional[str] = None,
                     tenant_id: Optional[int] = None,
                     commit: bool = True) -> BIMCostItem:
    """Creeaza un cost item pentru un element."""
    if cantitate < 0:
        raise ValueError('cantitate nu poate fi negativa')
    if pret_unitar < 0:
        raise ValueError('pret_unitar nu poate fi negativ')

    item = BIMCostItem(
        tenant_id=tenant_id,
        element_bim_id=element_bim_id,
        categorie=categorie,
        faza=faza,
        descriere=descriere.strip()[:300],
        unitate=unitate,
        cantitate=cantitate,
        pret_unitar=pret_unitar,
        tip=tip,
        valuta=valuta,
        referinta_extern=(referinta_extern or '').strip() or None,
        creat_de_id=getattr(user, 'id', None) if user else None,
    )
    db.session.add(item)
    db.session.flush()

    audit_svc.log_create('bim_cost_item', item.id, new_values={
        'element_bim_id': element_bim_id,
        'categorie': categorie,
        'cantitate': float(cantitate),
        'pret_unitar': float(pret_unitar),
        'total': item.total,
    })

    if commit:
        db.session.commit()
    return item


# ====================================================
# AGREGARE
# ====================================================

def cost_total_element(element_bim_id: int, tip: Optional[str] = None) -> dict:
    """
    Returneaza breakdown cost per element pe categorii.
    """
    q = BIMCostItem.query.filter_by(element_bim_id=element_bim_id)
    if tip:
        q = q.filter_by(tip=tip)
    items = q.all()

    by_cat = {}
    total = 0.0
    for it in items:
        t = it.total
        by_cat[it.categorie] = by_cat.get(it.categorie, 0.0) + t
        total += t
    return {
        'element_bim_id': element_bim_id,
        'total': round(total, 2),
        'by_categorie': {k: round(v, 2) for k, v in by_cat.items()},
        'count_items': len(items),
    }


def cost_breakdown_santier(santier_id: int, tip: Optional[str] = None) -> dict:
    """
    Breakdown cost total pentru un santier.
    Returneaza:
        {
            'total': X,
            'by_categorie': {...},
            'by_cladire': {cladire_id: total, ...},
            'by_disciplina': {ARH: total, STR: total, ...},
            'by_tip_element': {wall: total, door: total, ...}
        }
    """
    cladiri = Cladire.query.filter_by(santier_id=santier_id).all()
    cladire_ids = [c.id for c in cladiri]
    if not cladire_ids:
        return {'total': 0, 'by_categorie': {}, 'by_cladire': {},
                'by_disciplina': {}, 'by_tip_element': {}}

    q = (db.session.query(BIMCostItem, ElementBIM)
         .join(ElementBIM, ElementBIM.id == BIMCostItem.element_bim_id)
         .filter(ElementBIM.cladire_id.in_(cladire_ids)))
    if tip:
        q = q.filter(BIMCostItem.tip == tip)

    by_cat = {}
    by_cladire = {}
    by_tip_el = {}
    total = 0.0

    for cost_item, elem in q.all():
        t = cost_item.total
        total += t
        by_cat[cost_item.categorie] = by_cat.get(cost_item.categorie, 0.0) + t
        by_cladire[elem.cladire_id] = by_cladire.get(elem.cladire_id, 0.0) + t
        by_tip_el[elem.tip_element] = by_tip_el.get(elem.tip_element, 0.0) + t

    # Map cladire_id -> cod pentru afisare
    by_cladire_named = {}
    for c in cladiri:
        if c.id in by_cladire:
            by_cladire_named[f'{c.cod} - {c.nume}'] = round(by_cladire[c.id], 2)

    return {
        'total': round(total, 2),
        'by_categorie': {k: round(v, 2) for k, v in by_cat.items()},
        'by_cladire': by_cladire_named,
        'by_tip_element': {k: round(v, 2) for k, v in by_tip_el.items()},
    }


def cost_planificat_vs_real(santier_id: int) -> dict:
    """
    Compara cost planificat vs real pentru un santier.
    Returneaza:
        {
            'planificat': X,
            'real': Y,
            'delta': Y - X,
            'delta_pct': (Y - X) / X * 100,
        }
    """
    plan = cost_breakdown_santier(santier_id, tip='planificat')['total']
    real = cost_breakdown_santier(santier_id, tip='real')['total']
    delta = real - plan
    delta_pct = (delta / plan * 100) if plan > 0 else 0
    return {
        'planificat': plan,
        'real': real,
        'delta': round(delta, 2),
        'delta_pct': round(delta_pct, 1),
    }
