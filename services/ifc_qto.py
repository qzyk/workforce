"""
QTO (Quantity Take-Off) din BIM: genereaza o antemasuratoare (BoQ) din model.

Doua surse:
- qto_din_elemente(elemente): grupare pe tip_element din ElementBIM importate
  (count-based + cantitate daca e setata). Mereu disponibila.
- qto_din_ifc(file_path): imbogateste cu cantitati reale din BaseQuantities IFC
  (volum/arie/lungime), cand modelul le contine.

Inchide bucla BIM -> cantitati -> articole, exportabile in F3/Gantt/deviz.
"""
from __future__ import annotations


def _label_tipuri():
    from models import ElementBIM
    return {cod: lbl for cod, lbl, _ in getattr(ElementBIM, 'TIPURI', [])}


def qto_din_elemente(elemente) -> list:
    """[{tip, label, um, cantitate, nr}] - grupare pe tip (count + cantitate daca exista)."""
    label = _label_tipuri()
    grup = {}
    for e in elemente:
        g = grup.setdefault(e.tip_element, {'nr': 0, 'cant': 0.0, 'um': None})
        g['nr'] += 1
        if e.cantitate:
            g['cant'] += float(e.cantitate)
            g['um'] = e.unitate_masura or g['um']
    rows = []
    for tip, g in grup.items():
        has_q = g['cant'] > 0
        rows.append({'tip': tip, 'label': label.get(tip, tip),
                     'um': (g['um'] or 'buc') if has_q else 'buc',
                     'cantitate': round(g['cant'], 2) if has_q else g['nr'],
                     'nr': g['nr']})
    return sorted(rows, key=lambda r: -r['nr'])


# Tipuri masurabile volumetric (mc) — beton + elemente solide de cladire.
# Restul (armatura/plasa=kg, conducte=m, echipamente/usi=buc) NU se calculeaza
# geometric: e irelevant si lent. Asta accelereaza enorm modelele structurale.
VOLUMETRIC_TIPURI = {
    'slab', 'beam', 'column', 'wall', 'stair', 'footing', 'foundation',
    'covering', 'roof', 'ramp', 'pile', 'curtain_wall',
}


def _motor_geom():
    """(geom_module, settings, util_shape) sau (None, None, None) daca lipseste."""
    try:
        import ifcopenshell.geom as geom
        import ifcopenshell.util.shape as ushape
    except Exception:
        return None, None, None
    s = geom.settings()
    return geom, s, ushape


def _volum_geometric(inst, geom, settings, ushape):
    """Volum (mc) din geometria tesalata a elementului, sau None la esec."""
    try:
        sh = geom.create_shape(settings, inst)
        v = ushape.get_volume(sh.geometry)
        return float(v) if v and v > 0 else None
    except Exception:
        return None


def _cantitate_ifc(inst):
    """(cantitate, um) din BaseQuantities IFC, sau (None, None)."""
    prefs = [('VolumeValue', 'mc'), ('AreaValue', 'mp'), ('LengthValue', 'm'),
             ('WeightValue', 'kg'), ('CountValue', 'buc')]
    for rel in (getattr(inst, 'IsDefinedBy', None) or []):
        try:
            if not rel.is_a('IfcRelDefinesByProperties'):
                continue
            pd = rel.RelatingPropertyDefinition
            if not (pd and pd.is_a('IfcElementQuantity')):
                continue
            for attr, um in prefs:
                for q in (pd.Quantities or []):
                    v = getattr(q, attr, None)
                    if v:
                        return float(v), um
        except Exception:
            continue
    return None, None


def qto_din_ifc(file_path: str, geometric: bool = False,
                max_geom: int = 3000) -> list:
    """QTO cu cantitati reale din BaseQuantities (fallback count). [] la esec.

    geometric=True: pentru elementele FARA BaseQuantities calculeaza volumul (mc)
    din geometria tesalata (lent ~20ms/element). Plafonat la max_geom elemente
    procesate geometric; ce depaseste ramane count (raportat in 'nr_capat')."""
    try:
        import ifcopenshell
        from services.ifc_import import IFC_TYPE_MAP
    except Exception:
        return []
    try:
        f = ifcopenshell.open(file_path)
    except Exception:
        return []
    label = _label_tipuri()
    geom = settings = ushape = None
    if geometric:
        geom, settings, ushape = _motor_geom()
    geom_facute = 0       # cate volume am calculat geometric (buget global)
    grup = {}
    for ifc_type, tip in IFC_TYPE_MAP.items():
        try:
            instances = f.by_type(ifc_type)
        except Exception:
            continue
        for inst in instances:
            g = grup.setdefault(
                tip, {'nr': 0, 'cant': 0.0, 'um': None, 'nr_geom': 0, 'nr_capat': 0})
            g['nr'] += 1
            q, um = _cantitate_ifc(inst)
            if q:
                g['cant'] += q
                g['um'] = um or g['um']
            elif geom is not None and tip in VOLUMETRIC_TIPURI:
                # fara BaseQuantities -> incerc geometria (in limita bugetului)
                if geom_facute >= max_geom:
                    g['nr_capat'] += 1
                    continue
                v = _volum_geometric(inst, geom, settings, ushape)
                geom_facute += 1
                if v:
                    g['cant'] += v
                    g['um'] = g['um'] or 'mc'
                    g['nr_geom'] += 1
    rows = []
    for tip, g in grup.items():
        has_q = g['cant'] > 0
        rows.append({'tip': tip, 'label': label.get(tip, tip),
                     'um': (g['um'] or 'buc') if has_q else 'buc',
                     'cantitate': round(g['cant'], 2) if has_q else g['nr'],
                     'nr': g['nr'], 'nr_geom': g['nr_geom'],
                     'nr_capat': g['nr_capat']})
    return sorted(rows, key=lambda r: -r['nr'])
