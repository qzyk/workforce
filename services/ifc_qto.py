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


def qto_din_ifc(file_path: str) -> list:
    """QTO cu cantitati reale din BaseQuantities (fallback count). [] la esec."""
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
    grup = {}
    for ifc_type, tip in IFC_TYPE_MAP.items():
        try:
            instances = f.by_type(ifc_type)
        except Exception:
            continue
        for inst in instances:
            g = grup.setdefault(tip, {'nr': 0, 'cant': 0.0, 'um': None})
            g['nr'] += 1
            q, um = _cantitate_ifc(inst)
            if q:
                g['cant'] += q
                g['um'] = um or g['um']
    rows = []
    for tip, g in grup.items():
        has_q = g['cant'] > 0
        rows.append({'tip': tip, 'label': label.get(tip, tip),
                     'um': (g['um'] or 'buc') if has_q else 'buc',
                     'cantitate': round(g['cant'], 2) if has_q else g['nr'],
                     'nr': g['nr']})
    return sorted(rows, key=lambda r: -r['nr'])
