"""
Auto-pricing BIM (Faza 2): preturi de referinta 2026 pentru elemente IFC.

Flux: clasifica elementul (tip_element + material) -> categorie_lucrare + UM ->
cauta in catalogul PretReferinta (RON 2026) -> cost = cantitate x pret ->
BIMCostItem (via bim_5d). Agregare + TVA 21%.

Catalogul e EDITABIL; daca e gol, se populeaza cu valori 2026 orientative.
NU e feed live - valori curate, actualizabile.
"""

from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)

# Catalog default RON 2026 (orientativ, editabil din UI): (categorie, um) -> pret
CATALOG_2026 = [
    ('beton', 'mc', 750.0, 'Beton turnat (material + manopera), nivel 2026'),
    ('armatura', 'kg', 7.5, 'Armatura fasonata + montata'),
    ('confectii_metalice', 'kg', 16.0, 'Otel structural confectionat + montat'),
    ('cofraje', 'mp', 90.0, 'Cofraj + decofrare'),
    ('zidarie', 'mp', 220.0, 'Zidarie + mortar'),
    ('tencuiala', 'mp', 55.0, 'Tencuiala'),
    ('finisaje', 'mp', 120.0, 'Finisaje medii'),
    # fallback-uri pe UM pentru categoria 'diverse'
    ('diverse', 'mc', 500.0, 'Generic volumetric'),
    ('diverse', 'mp', 80.0, 'Generic pe arie'),
    ('diverse', 'm', 60.0, 'Generic liniar'),
    ('diverse', 'kg', 10.0, 'Generic masic'),
    ('diverse', 'buc', 100.0, 'Generic bucata'),
]

ARMATURA_TIPURI = {'reinforcingbar', 'reinforcingmesh', 'rebar', 'tendon'}
OTEL_TIPURI = {'beam', 'column', 'member', 'plate', 'brace'}
BETON_TIPURI = {'slab', 'beam', 'column', 'footing', 'foundation', 'pile', 'ramp', 'member', 'wall'}


def seed_catalog(tenant_id=None, commit=True):
    """Populeaza catalogul global (idempotent) cu valorile 2026 default."""
    from models import db, PretReferinta
    adaugate = 0
    for cat, um, pret, sursa in CATALOG_2026:
        exista = PretReferinta.query.filter_by(
            tenant_id=tenant_id, categorie_lucrare=cat, um=um).first()
        if exista:
            continue
        db.session.add(PretReferinta(
            tenant_id=tenant_id, categorie_lucrare=cat, um=um,
            pret_unitar=pret, sursa=sursa, an_referinta=2026))
        adaugate += 1
    if commit and adaugate:
        db.session.commit()
    return adaugate


def _ensure_catalog():
    from models import PretReferinta
    if PretReferinta.query.filter_by(tenant_id=None).count() == 0:
        seed_catalog(tenant_id=None)


def categorie_si_um(el):
    """Mapeaza un ElementBIM -> (categorie_lucrare, um) pentru pricing."""
    tip = (el.tip_element or '').lower()
    mat = (el.material or '').lower()
    um = (el.unitate_masura or '').lower() or None

    if tip in ARMATURA_TIPURI or any(k in mat for k in ('bst', 'pc52', 'pc60', 's500', 'armatur')):
        return 'armatura', um or 'kg'
    if tip in OTEL_TIPURI and any(k in mat for k in ('s235', 's275', 's355', 'otel', 'steel')):
        return 'confectii_metalice', um or 'kg'
    if 'beton' in mat or any(k in mat for k in ('c12', 'c16', 'c20', 'c25', 'c30', 'c35', 'c40')):
        return 'beton', um or 'mc'
    if tip == 'wall' or 'zid' in mat or 'caramid' in mat:
        return 'zidarie', um or 'mp'
    if tip in BETON_TIPURI:
        return 'beton', um or 'mc'
    return 'diverse', um or 'buc'


def pret_element(el, tenant_id=None):
    """Returneaza (pret_unitar | None, categorie, um) pentru un element."""
    from models import PretReferinta
    cat, um = categorie_si_um(el)
    if not um:
        return None, cat, um
    pr = (PretReferinta.query.filter_by(categorie_lucrare=cat, um=um, tenant_id=tenant_id).first()
          or PretReferinta.query.filter_by(categorie_lucrare=cat, um=um, tenant_id=None).first())
    return (float(pr.pret_unitar) if pr else None), cat, um


def genereaza_preturi_santier(santier_id, user, cota_tva=21):
    """
    Genereaza BIMCostItem pentru elementele cu cantitate ale santierului.
    Idempotent: sterge intai cost-urile auto anterioare. Returneaza rezumat + TVA.
    """
    from models import db, Cladire, ElementBIM, BIMCostItem
    from services import bim_5d

    _ensure_catalog()
    cladiri_ids = [c.id for c in Cladire.query.filter_by(santier_id=santier_id).all()]
    if not cladiri_ids:
        return {'status': 'eroare', 'mesaj': 'Niciun element pe santier (importa + leaga IFC).'}

    elems = ElementBIM.query.filter(
        ElementBIM.cladire_id.in_(cladiri_ids),
        ElementBIM.cantitate.isnot(None)).all()
    if not elems:
        return {'status': 'eroare',
                'mesaj': 'Elementele nu au cantitate. Ruleaza intai calculul de cantitati.'}

    ids = [e.id for e in elems]
    # idempotent: sterg cost-urile auto anterioare
    BIMCostItem.query.filter(
        BIMCostItem.element_bim_id.in_(ids),
        BIMCostItem.referinta_extern == 'auto-pricing-2026').delete(synchronize_session=False)

    total = 0.0
    n = 0
    fara_pret = 0
    by_cat = {}
    for el in elems:
        pret, cat, um = pret_element(el)
        if pret is None:
            fara_pret += 1
            continue
        cantitate = float(el.cantitate)
        bim_5d.create_cost_item(
            el.id, f'{cat} ({um})', cantitate, pret, user=user,
            categorie='material', unitate=um, valuta='RON',
            referinta_extern='auto-pricing-2026', commit=False)
        val = cantitate * pret
        total += val
        by_cat[cat] = round(by_cat.get(cat, 0.0) + val, 2)
        n += 1

    db.session.commit()
    tva = round(total * cota_tva / 100.0, 2)
    return {
        'status': 'ok',
        'nr_pretuite': n,
        'fara_pret': fara_pret,
        'total_fara_tva': round(total, 2),
        'cota_tva': cota_tva,
        'tva': tva,
        'total_cu_tva': round(total + tva, 2),
        'by_categorie': by_cat,
    }
