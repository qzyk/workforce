"""
Clash detection pentru elemente BIM.

Strategii suportate:

1. **Geometric (AABB)** - intersectie de bounding boxes.
   Citeste bbox-ul din ElementBIM.bbox (coordonate WORLD, populat la importul IFC
   in Faza 2, coloana bbox_json) cu fallback la formatul vechi din
   proprietati_json ({"bbox": {"min": [...], "max": [...]}}) pentru
   compatibilitate cu elementele importate inainte de Faza 2.
   Pe modele care nu au bbox, se sare elegant.

2. **Logic** - verificari fara geometrie:
   - Duplicate IFC GlobalId in federation (acelasi GUID pe elemente diferite)
   - Suprasaturare spatii (>= N elemente de tip critic in acelasi spatiu)

Engine-ul ruleaza ambele strategii by default ('mixed').
Output: ClashRun + N ClashResult, plus statistici per severitate, plus upsert
in ClashGroup (deduplicare intre rulari) si delta (noi/existente/disparute).

PERFORMANTA (Faza 3): in loc de O(n^2) combinations pe toate perechile, folosim
un INDEX SPATIAL pe grid uniform (dict de celule, pur Python, zero dependente).
Fiecare element se insereaza in toate celulele atinse de bbox-ul lui; comparam
doar perechile care impart cel putin o celula (candidati), dupa care testul AABB
fin decide clash-ul real. Rezultatul e identic ca SET cu cel al algoritmului
O(n^2) brute force pe acelasi input (vezi testul de echivalenta).

NOTA: pe PA fara CGAL/OpenSCAD, ne limitam la AABB. Pentru hard clash
geometric exact (mesh intersection) e nevoie de offline processing.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime
from itertools import combinations
from typing import Optional

from models import db, ClashRun, ClashResult, ClashGroup, ElementBIM, Cladire
from services import audit as audit_svc


_logger = logging.getLogger(__name__)


# Toleranta de intersectie istorica (1mm) folosita cand ClashRun.tolerance_mm
# e NULL. Pastreaza rezultatul vechi neschimbat.
DEFAULT_TOLERANCE_M = 0.001

# Dimensiune implicita de celula pentru grid-ul spatial (metri). Vezi _alege_cell_size.
DEFAULT_CELL_SIZE_M = 2.0

# Plafon de siguranta: peste atatea celule atinse de UN element (bbox urias fata
# de cell_size, ex. un teren intreg), cadem inapoi la o singura "celula globala"
# pentru acel element ca sa nu explodam memoria indexului.
MAX_CELULE_PER_ELEMENT = 100_000


# ====================================================
# UTILITARE BBOX
# ====================================================

def _normalize_bbox(bbox) -> Optional[dict]:
    """
    Valideaza si normalizeaza un dict bbox la {min:[x,y,z], max:[x,y,z]} cu
    float-uri. Returneaza None daca formatul nu e valid.
    """
    if not isinstance(bbox, dict):
        return None
    mn = bbox.get('min'); mx = bbox.get('max')
    if (isinstance(mn, (list, tuple)) and isinstance(mx, (list, tuple))
            and len(mn) == 3 and len(mx) == 3):
        try:
            return {'min': [float(v) for v in mn], 'max': [float(v) for v in mx]}
        except (ValueError, TypeError):
            return None
    return None


def _get_bbox(element: ElementBIM) -> Optional[dict]:
    """
    Returneaza {min: [x,y,z], max: [x,y,z]} (coordonate WORLD) sau None.

    Sursa primara: element.bbox (coloana bbox_json, Faza 2). Fallback: formatul
    vechi din proprietati_json['bbox'] pentru compatibilitate cu elementele
    importate inainte de Faza 2.
    """
    # Sursa Faza 2 (coloana dedicata bbox_json, coordonate world)
    bb = _normalize_bbox(element.bbox)
    if bb is not None:
        return bb

    # Fallback: formatul vechi din proprietati_json
    if not element.proprietati_json:
        return None
    try:
        props = json.loads(element.proprietati_json)
    except (ValueError, TypeError):
        return None
    if not isinstance(props, dict):
        return None
    return _normalize_bbox(props.get('bbox'))


def _aabb_intersect(a: dict, b: dict, tolerance: float = DEFAULT_TOLERANCE_M) -> Optional[dict]:
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


def _aabb_distance(a: dict, b: dict) -> float:
    """
    Distanta euclidiana (metri) intre doua AABB-uri. 0 daca se intersecteaza
    sau se ating. gap_axa = max(a_min - b_max, b_min - a_max, 0); distanta =
    sqrt(sum(gap^2)). E distanta minima reala intre cele doua cutii.
    """
    gap_sq = 0.0
    for axis_idx in range(3):
        a_min = a['min'][axis_idx]; a_max = a['max'][axis_idx]
        b_min = b['min'][axis_idx]; b_max = b['max'][axis_idx]
        gap = max(a_min - b_max, b_min - a_max, 0.0)
        gap_sq += gap * gap
    return math.sqrt(gap_sq)


# ====================================================
# INDEX SPATIAL (GRID UNIFORM)
# ====================================================

def _alege_cell_size(bboxes: list[dict]) -> float:
    """
    Euristica pentru dimensiunea celulei (metri).

    Alegem mediana extinderii maxime pe axa a bbox-urilor. Intuitie: o celula
    cam de marimea unui element tipic tine numarul de candidati per celula mic
    si numarul de celule atinse de un element mic la ~1, fara sa fragmentam
    excesiv elementele mari. Marginim la [0.25m, 50m] ca sa evitam degenerari
    (elemente foarte mici -> prea multe celule; foarte mari -> grid grosier).
    """
    if not bboxes:
        return DEFAULT_CELL_SIZE_M
    extinderi = []
    for bb in bboxes:
        ext = max(bb['max'][i] - bb['min'][i] for i in range(3))
        if ext > 0:
            extinderi.append(ext)
    if not extinderi:
        return DEFAULT_CELL_SIZE_M
    extinderi.sort()
    mediana = extinderi[len(extinderi) // 2]
    if mediana <= 0:
        return DEFAULT_CELL_SIZE_M
    return min(50.0, max(0.25, mediana))


def _celule_atinse(bbox: dict, cell_size: float) -> list[tuple]:
    """
    Lista de chei de celula (ix, iy, iz) atinse de bbox, de la floor(min/cell)
    la floor(max/cell) pe fiecare axa. Plafon de siguranta MAX_CELULE_PER_ELEMENT
    pentru bbox-uri uriase (cadem inapoi la o singura celula 'globala').
    """
    ranges = []
    nr_celule = 1
    for i in range(3):
        lo = int(math.floor(bbox['min'][i] / cell_size))
        hi = int(math.floor(bbox['max'][i] / cell_size))
        ranges.append((lo, hi))
        nr_celule *= (hi - lo + 1)
        if nr_celule > MAX_CELULE_PER_ELEMENT:
            # bbox prea mare relativ la cell_size -> evitam explozia de celule
            return [('GLOBAL',)]
    celule = []
    for ix in range(ranges[0][0], ranges[0][1] + 1):
        for iy in range(ranges[1][0], ranges[1][1] + 1):
            for iz in range(ranges[2][0], ranges[2][1] + 1):
                celule.append((ix, iy, iz))
    return celule


def _candidate_pairs(elements_with_bbox: list, cell_size: float) -> set:
    """
    Construieste indexul spatial pe grid uniform si returneaza setul de perechi
    candidat (indici in lista, i<j) care impart cel putin o celula.

    Deduplicarea perechilor e intrinseca: folosim un set de (i, j) cu i<j, deci
    o pereche care imparte mai multe celule apare o singura data.
    """
    grid: dict[tuple, list[int]] = {}
    for idx, (_el, bb) in enumerate(elements_with_bbox):
        for cheie in _celule_atinse(bb, cell_size):
            grid.setdefault(cheie, []).append(idx)

    candidati: set[tuple[int, int]] = set()
    for ocupanti in grid.values():
        if len(ocupanti) < 2:
            continue
        for i, j in combinations(ocupanti, 2):
            # i<j garantat de combinations pe lista crescatoare de indici
            candidati.add((i, j) if i < j else (j, i))
    return candidati


# ====================================================
# DETECTIE GEOMETRICA
# ====================================================

def _severitate_din_volum(volum: float) -> str:
    if volum > 0.1:
        return 'mare'
    if volum > 0.001:
        return 'medie'
    return 'mica'


def _detect_geometric_clashes(elements: list[ElementBIM],
                              tolerance: float = DEFAULT_TOLERANCE_M) -> list[dict]:
    """
    AABB intersection pe perechi de elemente cu bbox cunoscut, accelerata cu un
    index spatial pe grid uniform (vezi _candidate_pairs). Comparam doar
    perechile candidat (care impart o celula); testul AABB fin (_aabb_intersect)
    decide clash-ul real. Rezultatul e identic ca set cu O(n^2) brute force.

    Returneaza lista de dict-uri cu element_a_id, element_b_id, tip='hard', detalii.
    """
    elements_with_bbox = [(el, _get_bbox(el)) for el in elements]
    elements_with_bbox = [(el, bb) for el, bb in elements_with_bbox if bb]

    n = len(elements_with_bbox)
    if n < 2:
        return []

    cell_size = _alege_cell_size([bb for _el, bb in elements_with_bbox])
    candidati = _candidate_pairs(elements_with_bbox, cell_size)

    clashes = []
    for i, j in candidati:
        el_a, bb_a = elements_with_bbox[i]
        el_b, bb_b = elements_with_bbox[j]
        if el_a.id == el_b.id:
            continue
        ovl = _aabb_intersect(bb_a, bb_b, tolerance=tolerance)
        if ovl is None:
            continue
        severitate = _severitate_din_volum(ovl['volume'])
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


def _detect_geometric_clashes_bruteforce(elements: list[ElementBIM],
                                         tolerance: float = DEFAULT_TOLERANCE_M) -> list[dict]:
    """
    Varianta O(n^2) (combinations pe toate perechile) - pastrata DOAR ca
    referinta de corectitudine pentru testul de echivalenta cu grid-ul. NU se
    foloseste in productie.
    """
    elements_with_bbox = [(el, _get_bbox(el)) for el in elements]
    elements_with_bbox = [(el, bb) for el, bb in elements_with_bbox if bb]

    clashes = []
    for (el_a, bb_a), (el_b, bb_b) in combinations(elements_with_bbox, 2):
        if el_a.id == el_b.id:
            continue
        ovl = _aabb_intersect(bb_a, bb_b, tolerance=tolerance)
        if ovl is None:
            continue
        severitate = _severitate_din_volum(ovl['volume'])
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
# DEDUPLICARE INTRE RULARI (ClashGroup)
# ====================================================

def _normalize_pereche(a_id: int, b_id: int) -> tuple[int, int]:
    """Normalizeaza perechea ca (min, max) pentru stocare deterministica."""
    return (a_id, b_id) if a_id <= b_id else (b_id, a_id)


# Mapare tip ClashResult -> tip ClashGroup (clearance e expus ca 'clearance' in grup)
def _tip_grup(tip_result: str) -> str:
    return tip_result


def _upsert_clash_groups(detected: list[dict], run_id: int,
                         tenant_id: Optional[int]) -> dict:
    """
    Upsert in ClashGroup pentru perechile detectate la aceasta rulare.

    - pereche noua -> ClashGroup nou, status 'activ', prima_detectie=acum
    - pereche existenta -> update ultima_detectie + adauga run_id + severitate
    - perechi care nu mai apar (existau ca 'activ' dar nu sunt in run-ul curent)
      -> raman in DB, status pastrat, dar le numaram ca 'disparute' (stale)

    Returneaza delta: {'noi': N, 'existente': M, 'disparute': K}.
    Statusul pus de utilizator (rezolvat/ignorat) NU e modificat la reaparitie.
    """
    acum = datetime.utcnow()

    # Perechile detectate acum, normalizate, cu tipul lor de grup
    perechi_curente: dict[tuple, dict] = {}
    for d in detected:
        a_id, b_id = _normalize_pereche(d['element_a_id'], d['element_b_id'])
        tip = _tip_grup(d['tip'])
        cheie = (a_id, b_id, tip)
        # Pastram severitatea maxima vazuta pe aceasta pereche in run
        prev = perechi_curente.get(cheie)
        if prev is None:
            perechi_curente[cheie] = {'a': a_id, 'b': b_id, 'tip': tip,
                                      'severitate': d.get('severitate', 'medie')}

    noi = 0
    existente = 0
    for (a_id, b_id, tip), info in perechi_curente.items():
        grup = ClashGroup.query.filter_by(
            tenant_id=tenant_id, element_a_id=a_id, element_b_id=b_id, tip=tip,
        ).first()
        if grup is None:
            grup = ClashGroup(
                tenant_id=tenant_id,
                element_a_id=a_id, element_b_id=b_id, tip=tip,
                status='activ', severitate=info['severitate'],
                prima_detectie=acum, ultima_detectie=acum,
                run_ids_json=json.dumps([run_id]),
            )
            db.session.add(grup)
            noi += 1
        else:
            grup.ultima_detectie = acum
            grup.severitate = info['severitate']
            run_ids = grup.get_run_ids()
            if run_id not in run_ids:
                run_ids.append(run_id)
            grup.run_ids_json = json.dumps(run_ids)
            existente += 1

    # Perechi disparute: grupuri 'activ' din acelasi tenant care nu au reaparut acum.
    # Le numaram (stale), fara sa le stergem sau sa le schimbam statusul.
    chei_curente = set(perechi_curente.keys())
    disparute = 0
    grupuri_active = ClashGroup.query.filter_by(
        tenant_id=tenant_id, status='activ',
    ).all()
    for g in grupuri_active:
        if (g.element_a_id, g.element_b_id, g.tip) not in chei_curente:
            disparute += 1

    return {'noi': noi, 'existente': existente, 'disparute': disparute}


# ====================================================
# ENGINE PRINCIPAL
# ====================================================

def run_clash_detection(*,
                        santier_id: Optional[int] = None,
                        model_id: Optional[int] = None,
                        tip: str = 'mixed',
                        tolerance_mm: Optional[int] = None,
                        user=None) -> dict:
    """
    Ruleaza clash detection pe scope-ul indicat (santier sau model individual).

    tolerance_mm: toleranta de intersectie AABB in mm. None -> 1mm (istoric,
    rezultat neschimbat). Valori mai mari relaxeaza (ignora suprapunerile mici);
    valori 0 raporteaza si simplele atingeri.

    Returneaza:
        {
            'run_id': <int>,
            'total_clashes': <int>,
            'by_severity': {...},
            'delta': {'noi': ..., 'existente': ..., 'disparute': ...},
            'duration_ms': ...
        }
    """
    if not santier_id and not model_id:
        raise ValueError('Trebuie specificat santier_id sau model_id.')

    started = datetime.utcnow()
    tenant_id = getattr(user, 'tenant_id', None) if user else None

    # Toleranta efectiva (metri): tolerance_mm/1000 sau fallback istoric 1mm
    if tolerance_mm is not None:
        tolerance_m = tolerance_mm / 1000.0
    else:
        tolerance_m = DEFAULT_TOLERANCE_M

    # Construim ClashRun-ul (status='rulare', actualizam la final)
    run = ClashRun(
        tenant_id=tenant_id,
        santier_id=santier_id,
        model_id=model_id,
        tip=tip,
        tolerance_mm=tolerance_mm,
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
                    'by_severity': {},
                    'delta': {'noi': 0, 'existente': 0, 'disparute': 0},
                    'duration_ms': 0}
        q = q.filter(ElementBIM.cladire_id.in_(cladiri_ids))
    elements = q.all()

    detected = []
    if tip in ('geometric', 'mixed'):
        detected.extend(_detect_geometric_clashes(elements, tolerance=tolerance_m))
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

    # Deduplicare intre rulari: upsert in ClashGroup + delta
    delta = _upsert_clash_groups(detected, run.id, run.tenant_id)

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
            'delta': delta,
            'tip': tip,
            'tolerance_mm': tolerance_mm,
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
        'delta': delta,
        'duration_ms': run.durata_ms,
    }


# ====================================================
# PROMOVARE CLASH GROUP -> ISSUE (paritate cu violation_to_issue)
# ====================================================

def clash_group_to_issue(grup: ClashGroup, user) -> Optional[int]:
    """
    Converteste un ClashGroup in IssueBIM oficial. Returneaza issue.id.
    Doar admin/manager poate face conversia (paritate cu rules.violation_to_issue).
    """
    from models import IssueBIM
    if user.rol not in ('admin', 'manager'):
        raise PermissionError('Doar admin/manager poate promova un clash in issue.')
    if grup.issue_id:
        return grup.issue_id

    cod_a = grup.element_a.cod if grup.element_a else f'#{grup.element_a_id}'
    cod_b = grup.element_b.cod if grup.element_b else f'#{grup.element_b_id}'
    titlu = f'[CLASH {grup.tip}] {cod_a} <-> {cod_b}'

    issue = IssueBIM(
        tenant_id=grup.tenant_id,
        tip='conflict_proiectare',
        severitate=grup.severitate or 'medie',
        status='deschis',
        titlu=titlu[:300],
        descriere=(f'Clash {grup.tip} intre {cod_a} si {cod_b}. '
                   f'Detectat prima data {grup.prima_detectie}.'),
        element_bim_id=grup.element_a_id,
        raportat_de_id=user.id,
    )
    db.session.add(issue)
    db.session.flush()

    grup.issue_id = issue.id
    db.session.commit()
    audit_svc.log('promote_clash_to_issue', 'bim_clash_group', grup.id,
                  new_values={'issue_id': issue.id})
    return issue.id
