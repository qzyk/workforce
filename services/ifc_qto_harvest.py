"""
Harvest QTO din BaseQuantities STOCATE in IFC -> ElementBIM (Etapa 1: punte IFC -> F3).

Citeste cantitatile de baza (volum/arie/lungime/greutate) direct din quantity-set-urile
stocate in model (NU recalcul geometric), le scrie pe ElementBIM impreuna cu:
  - cod_deviz / clasificare_sursa  (mapare element -> categorie deviz, stratificata)
  - qto_sursa / qto_set            (provenienta cantitatii, trasabilitate)
  - necesita_verificare / motiv    (goluri + elemente multistrat = risc double-count)
GlobalId (ElementBIM.ifc_global_id) e cheia de trasabilitate pe fiecare rand.

Ruleaza OFFLINE (flask qto-harvest), niciodata in request HTTP. Web-ul citeste
ElementBIM precomputat (legatura_bim/cost_element_bim raman neschimbate).

Decizii: vezi nota Obsidian "Decizie tehnica - Punte IFC to F3 (Etapa 1)".
Capcane verificate: get_psets() intoarce si cheia "id" (cerem campul direct);
match EXACT pe numele setului (evita seturi custom); get_material() (NU
get_material_layers, care nu exista); fara recompute geometric pe PA.
"""
from __future__ import annotations

import gc
import os
from datetime import datetime


# tip_element -> [Qto set EXACT, camp cantitate, U.M.]. Override via config/gantt/qto_sets.json.
DEFAULT_QTO_SETS = {
    'slab': ['Qto_SlabBaseQuantities', 'NetVolume', 'mc'],
    'beam': ['Qto_BeamBaseQuantities', 'NetVolume', 'mc'],
    'column': ['Qto_ColumnBaseQuantities', 'NetVolume', 'mc'],
    'wall': ['Qto_WallBaseQuantities', 'NetVolume', 'mc'],
    'footing': ['Qto_FootingBaseQuantities', 'NetVolume', 'mc'],
    'pile': ['Qto_PileBaseQuantities', 'NetVolume', 'mc'],
    'covering': ['Qto_CoveringBaseQuantities', 'NetArea', 'mp'],
    'curtain_wall': ['Qto_CurtainWallBaseQuantities', 'NetArea', 'mp'],
    'rebar': ['Qto_ReinforcingElementBaseQuantities', 'Weight', 'kg'],
    'mesh': ['Qto_ReinforcingElementBaseQuantities', 'Weight', 'kg'],
    'pipe': ['Qto_PipeSegmentBaseQuantities', 'Length', 'm'],
    'duct': ['Qto_DuctSegmentBaseQuantities', 'Length', 'm'],
    'member': ['Qto_MemberBaseQuantities', 'NetVolume', 'mc'],
    'plate': ['Qto_PlateBaseQuantities', 'NetWeight', 'kg'],
}

# Tipuri unde 'buc' E cantitatea corecta (NU le flag-uim ca "fara cantitate").
COUNT_TIPURI = {
    'door', 'window', 'AHU', 'chiller', 'fan', 'pump', 'valve', 'sensor',
    'light', 'outlet', 'switch', 'panel', 'sprinkler', 'extinguisher',
    'elevator', 'cable_tray', 'fastener', 'railing', 'proxy',
}


def _qto_sets() -> dict:
    out = {k: list(v) for k, v in DEFAULT_QTO_SETS.items()}
    try:
        from services.gantt import config_loader as cfg
        data = cfg.incarca('qto_sets', {}) or {}
        for k, v in data.items():
            if not str(k).startswith('_') and isinstance(v, list) and len(v) == 3:
                out[k] = v
    except Exception:
        pass
    return out


def _clasificare_map() -> dict:
    try:
        from services.gantt import config_loader as cfg
        data = cfg.incarca('clasificare_deviz', {}) or {}
        return data.get('mappings', {}) if isinstance(data, dict) else {}
    except Exception:
        return {}


def _match_clas(code, clas_map):
    c = str(code or '').strip().lower()
    if not c:
        return None
    for k, v in clas_map.items():
        kl = str(k).lower()
        if kl and (c.startswith(kl) or kl in c):
            return v
    return None


def _cantitate_qto(el, ue, ifc_set, camp):
    """(valoare, set_gasit_bool) din quantity-set STOCAT. (None, False) daca lipseste setul,
    (None, True) daca setul exista dar campul lipseste. Nu recalculeaza geometrie."""
    try:
        qtos = ue.get_psets(el, qtos_only=True)
    except Exception:
        return None, False
    if not qtos:
        return None, False
    qset = qtos.get(ifc_set)          # match EXACT pe nume (evita seturi custom)
    if not isinstance(qset, dict):
        return None, False
    val = qset.get(camp)             # cerem campul direct -> cheia "id" e ignorata
    if val is None:
        return None, True
    try:
        return float(val), True
    except (TypeError, ValueError):
        return None, True


def _e_compus(el, ue) -> bool:
    """True daca elementul are material layer set cu >1 strat (risc de double-count)."""
    try:
        mat = ue.get_material(el)     # NU get_material_layers (nu exista in util.element)
    except Exception:
        return False
    if not mat:
        return False
    try:
        if mat.is_a('IfcMaterialLayerSetUsage'):
            return len(mat.ForLayerSet.MaterialLayers or []) > 1
        if mat.is_a('IfcMaterialLayerSet'):
            return len(mat.MaterialLayers or []) > 1
    except Exception:
        return False
    return False


def _categorie_deviz(el, ue, tip, clas_map, tip_f2):
    """(categorie|None, sursa). Stratificat: classification -> Pset Reference -> TIP_F2 -> neclasificat."""
    # 1. Clasificare explicita in IFC
    try:
        import ifcopenshell.util.classification as uc
        for ref in (uc.get_references(el) or []):
            code = (getattr(ref, 'Identification', None)
                    or getattr(ref, 'ItemReference', None))
            cat = _match_clas(code, clas_map)
            if cat:
                return cat, 'classification'
    except Exception:
        pass
    # 2. Pset_*Common.Reference (fallback oficial buildingSMART)
    try:
        for name, vals in (ue.get_psets(el) or {}).items():
            if str(name).endswith('Common') and isinstance(vals, dict):
                cat = _match_clas(vals.get('Reference'), clas_map)
                if cat:
                    return cat, 'pset_reference'
    except Exception:
        pass
    # 3. Euristica IfcType -> tip_element -> categorie F2 (comportamentul actual)
    cat = tip_f2.get(tip)
    if cat:
        return cat, 'heuristic'
    # 4. Neclasificat -> review manual
    return None, 'neclasificat'


def harvest_model(model_bim, root_path: str = '') -> dict:
    """Citeste BaseQuantities din IFC-ul lui model_bim si le scrie pe ElementBIM
    (potrivire pe GlobalId). Returneaza statistici. Degradeaza gratios."""
    try:
        import ifcopenshell
        import ifcopenshell.util.element as ue
        from services.ifc_import import IFC_TYPE_MAP
        from services.legatura_bim import TIP_F2
        from models import ElementBIM, db
    except Exception as e:
        return {'ok': False, 'motiv': f'ifcopenshell indisponibil: {e}'}

    path = model_bim.fisier_path or ''
    if path and not os.path.isabs(path):
        path = os.path.join(root_path or '', path)
    if not path or not os.path.exists(path):
        return {'ok': False, 'motiv': f'fisier inexistent: {path}'}

    try:
        f = ifcopenshell.open(path)
    except Exception as e:
        return {'ok': False, 'motiv': f'open esuat: {e}'}

    schema = getattr(f, 'schema', None)
    qsets = _qto_sets()
    clas = _clasificare_map()
    el_db = {e.ifc_global_id: e for e in
             ElementBIM.query.filter(ElementBIM.ifc_global_id.isnot(None)).all()}

    stat = {'elemente': 0, 'cu_cantitate': 0, 'count_buc': 0, 'de_verificat': 0,
            'fara_cantitate': 0, 'multistrat': 0, 'neclasificat': 0}
    try:
        for ifc_type, tip in IFC_TYPE_MAP.items():
            try:
                instances = f.by_type(ifc_type)
            except Exception:
                continue
            cfg = qsets.get(tip)
            for inst in instances:
                el = el_db.get(getattr(inst, 'GlobalId', None))
                if not el:
                    continue
                stat['elemente'] += 1
                el.model_bim_id = el.model_bim_id or model_bim.id
                el.source_system = el.source_system or 'ifc'
                el.necesita_verificare = False
                el.motiv_verificare = None
                motive = []

                # --- cantitate ---
                if cfg:
                    ifc_set, camp, um = cfg
                    val, set_found = _cantitate_qto(inst, ue, ifc_set, camp)
                    if val is not None and val > 0:
                        el.cantitate = val
                        el.unitate_masura = um
                        el.qto_sursa = 'ifc_basequantity'
                        el.qto_set = ifc_set
                        stat['cu_cantitate'] += 1
                    else:
                        el.qto_sursa = 'lipsa'
                        el.qto_set = ifc_set if set_found else None
                        motive.append(f'fara {ifc_set}' if not set_found else f'{camp} absent')
                        stat['fara_cantitate'] += 1
                else:
                    el.unitate_masura = el.unitate_masura or 'buc'
                    el.qto_sursa = 'count'
                    stat['count_buc'] += 1

                # --- mapare categorie deviz ---
                cat, sursa = _categorie_deviz(inst, ue, tip, clas, TIP_F2)
                el.cod_deviz = cat
                el.clasificare_sursa = sursa
                if cat is None:
                    motive.append('neclasificat')
                    stat['neclasificat'] += 1

                # --- detector elemente compuse (double-count) ---
                if _e_compus(inst, ue):
                    motive.append('element multistrat (risc double-count)')
                    stat['multistrat'] += 1

                if motive:
                    el.necesita_verificare = True
                    el.motiv_verificare = '; '.join(motive)[:120]
                    stat['de_verificat'] += 1
                el.last_synced_at = datetime.utcnow()
        db.session.commit()
    finally:
        del f
        gc.collect()

    return {'ok': True, 'schema': schema, 'model_id': model_bim.id, 'stat': stat}


def ciorna_review(model_id: int) -> dict:
    """Ciorna F3 din elementele harvestate ale unui model: agregat pe categorie
    (cod_deviz) + lista de elemente care necesita verificare (cu GlobalId)."""
    from models import ElementBIM, ModelBIM
    model = ModelBIM.query.get(model_id)
    elemente = ElementBIM.query.filter_by(model_bim_id=model_id).all()

    grup = {}
    de_verificat = []
    stat = {'elemente': len(elemente), 'cu_cantitate': 0, 'de_verificat': 0}
    for e in elemente:
        cat = e.cod_deviz or 'neclasificat'
        g = grup.setdefault(cat, {'categorie': cat, 'cantitate': 0.0, 'um': None,
                                  'nr': 0, 'de_verificat': 0})
        g['nr'] += 1
        um = e.unitate_masura
        if e.cantitate and um and um != 'buc':
            g['cantitate'] += float(e.cantitate)
            g['um'] = um
            stat['cu_cantitate'] += 1
        if e.necesita_verificare:
            g['de_verificat'] += 1
            stat['de_verificat'] += 1
            de_verificat.append({
                'cod': e.cod, 'nume': e.nume or e.cod, 'tip': e.tip_element,
                'cantitate': float(e.cantitate) if e.cantitate else None,
                'um': um, 'qto_sursa': e.qto_sursa, 'cod_deviz': e.cod_deviz,
                'motiv': e.motiv_verificare, 'global_id': e.ifc_global_id,
            })
    categorii = sorted(grup.values(), key=lambda r: (-r['nr']))
    for g in categorii:
        g['cantitate'] = round(g['cantitate'], 2)
        g['um'] = g['um'] or 'buc'
    return {'model': model, 'model_id': model_id, 'nr_elemente': len(elemente),
            'stat': stat, 'categorii': categorii, 'de_verificat': de_verificat}
