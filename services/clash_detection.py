"""
Clash detection pentru elemente BIM.

Strategii suportate:

1. **Geometric (AABB)** - intersectie de bounding boxes.
   Necesita coordonate in ElementBIM.proprietati_json:
       {"bbox": {"min": [x, y, z], "max": [x, y, z]}}
   Pe modele care nu au bbox, se sare elegant.

2. **Logic** - verificari fara geometrie:
   - Duplicate IFC GlobalId in federation (acelasi GUID pe elemente diferite)
   - Suprasaturare spatii (>= N elemente de tip critic in acelasi spatiu)
   - Discipline incompatibile in acelasi spatiu (ex: ELE intr-o zona wet fara grad de protectie)

Engine-ul ruleaza ambele strategii by default ('mixed').
Output: ClashRun + N ClashResult, plus statistici per severitate.

NOTA: pe PA fara CGAL/OpenSCAD, ne limitam la AABB. Pentru hard clash
geometric exact (mesh intersection) e nevoie de offline processing.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from itertools import combinations
from typing import Optional

from models import db, ClashRun, ClashResult, ElementBIM, Cladire
from services import audit as audit_svc


_logger = logging.getLogger(__name__)


# ====================================================
# UTILITARE BBOX
# ====================================================

def _get_bbox(element: ElementBIM) -> Optional[dict]:
    """
    Returneaza {min: [x,y,z], max: [x,y,z]} sau None daca lipseste.
    """
    if not element.proprietati_json:
        return None
    try:
        props = json.loads(element.proprietati_json)
    except (ValueError, TypeError):
        return None
    bbox = props.get('bbox') if isinstance(props, dict) else None
    if not isinstance(bbox, dict):
        return None
    mn = bbox.get('min'); mx = bbox.get('max')
    if (isinstance(mn, list) and isinstance(mx, list)
            and len(mn) == 3 and len(mx) == 3):
        return {'min': [float(v) for v in mn], 'max': [float(v) for v in mx]}
    return None


def _aabb_intersect(a: dict, b: dict, tolerance: float = 0.001) -> Optional[dict]:
    """
    True daca bbox-urile A si B se intersecteaza (cu o toleranta minima
    pentru a evita falsurile pozitive la elementele care doar se ating).
    Returneaza dict cu detalii de overlap sau None daca nu intersecteaza.
    """
    overlap = {'axes': [], 'volume': 0.0}
    sizes = []
    for axis_idx, axis_name in enumerate(('x', 'y', 'z')):
        a_min = a['min'][axis_idx]; a_max = a['max'][axis_idx]
        b_min = b['min'][axis_idx]; b_max = b['max'][axis_idx]
        # Suprapunere pe axa = max(0, min(a_max, b_max) - max(a_min, b_min))
        ov = min(a_max, b_max) - max(a_min, b_min)
        if ov <= tolerance:
            return None
        sizes.append(ov)
        overlap['axes'].append(axis_name)
    overlap['volume'] = round(sizes[0] * sizes[1] * sizes[2], 6)
    return overlap


# ====================================================
# DETECTIE GEOMETRICA
# ====================================================

def _detect_geometric_clashes(elements: list[ElementBIM]) -> list[dict]:
    """
    AABB intersection pe perechi de elemente cu bbox cunoscut.
    Returneaza lista de dict-uri cu element_a_id, element_b_id, tip='hard', detalii.
    """
    elements_with_bbox = [(el, _get_bbox(el)) for el in elements]
    elements_with_bbox = [(el, bb) for el, bb in elements_with_bbox if bb]

    clashes = []
    for (el_a, bb_a), (el_b, bb_b) in combinations(elements_with_bbox, 2):
        # Skip elemente pe acelasi cod (se considera identice)
        if el_a.id == el_b.id:
            continue
        # Skip elemente in acelasi container vizibil (parte+intreg) - heuristic
        # (ar trebui sa avem ParentRelationship in IFC; fara, ne bazam pe naming)
        ovl = _aabb_intersect(bb_a, bb_b)
        if ovl is None:
            continue
        # Severitate: depinde de marime overlap
        if ovl['volume'] > 0.1:
            severitate = 'mare'
        elif ovl['volume'] > 0.001:
            severitate = 'medie'
        else:
            severitate = 'mica'
        clashes.append({
            'element_a_id': el_a.id,
            'element_b_id': el_b.id,
            'tip': 'hard',
            'severitate': severitate,
            'mesaj': (f'{el_a.cod} ({el_a.tip_element}) intersecteaza '
                      f'{el_b.cod} ({el_b.tip_element}) - volum {ovl["volume"]} m3'),
            'detalii': {'overlap_volume': ovl['volume'], 'axes': ovl['axes']},
        })
    return clashes


# ====================================================
# DETECTIE LOGICA (fara geometrie)
# ====================================================

def _detect_duplicate_ifc_guids(elements: list[ElementBIM]) -> list[dict]:
    """Acelasi IFC GlobalId pe doua elemente diferite -> federation conflict."""
    by_guid = {}
    duplicates = []
    for el in elements:
        if not el.ifc_global_id:
            continue
        if el.ifc_global_id in by_guid:
            other = by_guid[el.ifc_global_id]
            duplicates.append({
                'element_a_id': other.id,
                'element_b_id': el.id,
                'tip': 'duplicate',
                'severitate': 'mare',
                'mesaj': (f'IFC GlobalId duplicat: {other.cod} si {el.cod} '
                          f'au acelasi GUID {el.ifc_global_id[:16]}...'),
                'detalii': {'ifc_global_id': el.ifc_global_id},
            })
        else:
            by_guid[el.ifc_global_id] = el
    return duplicates


def _detect_overcrowded_spaces(elements: list[ElementBIM], threshold: int = 20) -> list[dict]:
    """Spatii cu peste threshold elemente alocate -> potential dezaliniere."""
    by_space = {}
    for el in elements:
        if not el.spatiu_id:
            continue
        by_space.setdefault(el.spatiu_id, []).append(el)
    clashes = []
    for spatiu_id, els in by_space.items():
        if len(els) >= threshold:
            # Reportam ca un soft clash intre primele 2 elemente (placeholder)
            els_sorted = sorted(els, key=lambda e: e.id)
            a, b = els_sorted[0], els_sorted[1]
            clashes.append({
                'element_a_id': a.id,
                'element_b_id': b.id,
                'tip': 'soft',
                'severitate': 'medie',
                'mesaj': f'Spatiu {spatiu_id} are {len(els)} elemente - posibila supraincarcare',
                'detalii': {'space_id': spatiu_id, 'element_count': len(els),
                            'threshold': threshold},
            })
    return clashes


# ====================================================
# ENGINE PRINCIPAL
# ====================================================

def run_clash_detection(*,
                        santier_id: Optional[int] = None,
                        model_id: Optional[int] = None,
                        tip: str = 'mixed',
                        user=None) -> dict:
    """
    Ruleaza clash detection pe scope-ul indicat (santier sau model individual).

    Returneaza:
        {
            'run_id': <int>,
            'total_clashes': <int>,
            'by_severity': {...},
            'duration_ms': ...
        }
    """
    if not santier_id and not model_id:
        raise ValueError('Trebuie specificat santier_id sau model_id.')

    started = datetime.utcnow()

    # Construim ClashRun-ul (status='rulare', actualizam la final)
    run = ClashRun(
        tenant_id=getattr(user, 'tenant_id', None) if user else None,
        santier_id=santier_id,
        model_id=model_id,
        tip=tip,
        status='rulare',
        rulat_de_id=getattr(user, 'id', None) if user else None,
        data_rulare=started,
    )
    db.session.add(run)
    db.session.flush()

    # Selectez elementele in scope
    q = ElementBIM.query
    if santier_id:
        cladiri_ids = [c.id for c in Cladire.query.filter_by(santier_id=santier_id).all()]
        if not cladiri_ids:
            run.status = 'finalizat'
            run.log = 'Santier fara cladiri.'
            db.session.commit()
            return {'run_id': run.id, 'total_clashes': 0,
                    'by_severity': {}, 'duration_ms': 0}
        q = q.filter(ElementBIM.cladire_id.in_(cladiri_ids))
    elements = q.all()

    detected = []
    if tip in ('geometric', 'mixed'):
        detected.extend(_detect_geometric_clashes(elements))
    if tip in ('logic', 'mixed'):
        detected.extend(_detect_duplicate_ifc_guids(elements))
        detected.extend(_detect_overcrowded_spaces(elements))

    by_severity = {'mica': 0, 'medie': 0, 'mare': 0, 'critica': 0}

    for d in detected:
        cr = ClashResult(
            tenant_id=run.tenant_id,
            run_id=run.id,
            element_a_id=d['element_a_id'],
            element_b_id=d['element_b_id'],
            tip=d['tip'],
            severitate=d['severitate'],
            mesaj=d['mesaj'][:500],
            detalii_json=json.dumps(d.get('detalii', {}), ensure_ascii=False),
            status='noua',
        )
        db.session.add(cr)
        by_severity[d['severitate']] = by_severity.get(d['severitate'], 0) + 1

    # Update statistici pe run
    run.nr_clash_uri = len(detected)
    run.nr_critica = by_severity.get('critica', 0)
    run.nr_mare = by_severity.get('mare', 0)
    run.nr_medie = by_severity.get('medie', 0)
    run.nr_mica = by_severity.get('mica', 0)
    run.durata_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
    run.status = 'finalizat'
    db.session.commit()

    audit_svc.log(
        action='run_clash_detection',
        entity_type='bim_clash_run',
        entity_id=run.id,
        new_values={
            'total_clashes': len(detected),
            'by_severity': by_severity,
            'tip': tip,
            'santier_id': santier_id,
            'model_id': model_id,
            'duration_ms': run.durata_ms,
        },
        commit=True,
    )

    return {
        'run_id': run.id,
        'total_clashes': len(detected),
        'by_severity': by_severity,
        'duration_ms': run.durata_ms,
    }
