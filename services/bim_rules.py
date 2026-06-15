"""
Rule engine pentru model checking BIM.

DSL JSON declarativ. Fiecare BIMRule are:
- selector: ce elemente alege (filtru pe ElementBIM)
- constraint: conditia care trebuie indeplinita

Tipuri de reguli suportate:
1. required_properties:
     selector: {"tip_element": "wall"}
     constraint: {"required_properties": ["fire_rating", "thickness"]}

2. naming_convention:
     selector: {"tip_element": "door"}
     constraint: {"name_regex": "^USA-\\d{3}$"}

3. forbidden_in_zone:
     selector: {"tip_element": "panel"}
     constraint: {"zone_categories_forbidden": ["wet", "outdoor"]}

4. min_clearance:
     selector: {"tip_element": "duct"}
     constraint: {"min_distance_to": "wall", "value_m": 0.10}
     (necesita coordonate AABB; placeholder pentru moment)

Engine-ul ruleaza toate regulile active si genereaza RuleViolation-uri
intr-un singur "run" (run_id = UUID generat la apel).
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any, Optional

from models import db, BIMRule, RuleViolation, ElementBIM, Spatiu
from services import audit as audit_svc


_logger = logging.getLogger(__name__)


# ====================================================
# UTILITARE
# ====================================================

def _get_element_props(element: ElementBIM) -> dict:
    """Parseaza ElementBIM.proprietati_json -> dict."""
    if not element.proprietati_json:
        return {}
    try:
        data = json.loads(element.proprietati_json)
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def _select_elements(selector: dict, scope_filter: Optional[dict] = None) -> list[ElementBIM]:
    """
    Aplica selector-ul + scope-ul (optional, ex: {"santier_id": 5})
    pentru a obtine lista de ElementBIM-uri pe care se aplica regula.
    """
    q = ElementBIM.query

    if selector.get('tip_element'):
        q = q.filter(ElementBIM.tip_element == selector['tip_element'])
    if selector.get('status'):
        q = q.filter(ElementBIM.status == selector['status'])
    if selector.get('cladire_id'):
        q = q.filter(ElementBIM.cladire_id == selector['cladire_id'])

    # Scope (ex: limitam la elementele unui santier)
    if scope_filter:
        if scope_filter.get('santier_id'):
            from models import Cladire
            cladiri_ids = [c.id for c in Cladire.query.filter_by(santier_id=scope_filter['santier_id']).all()]
            if cladiri_ids:
                q = q.filter(ElementBIM.cladire_id.in_(cladiri_ids))
            else:
                return []  # niciun cladire pe santier

    return q.all()


# ====================================================
# EVALUATOARE PER TIP REGULA
# ====================================================

def _eval_required_properties(rule: BIMRule, definition: dict, scope: Optional[dict]) -> list[dict]:
    """Toate elementele selectate trebuie sa aiba proprietatile cerute (non-empty)."""
    selector = definition.get('selector', {})
    constraint = definition.get('constraint', {})
    required = constraint.get('required_properties', [])
    if not required:
        return []

    violations = []
    for el in _select_elements(selector, scope):
        props = _get_element_props(el)
        missing = [p for p in required if not props.get(p)]
        if missing:
            violations.append({
                'element_bim_id': el.id,
                'mesaj': f'{el.cod}: lipsesc proprietatile {missing}',
                'detalii': {'missing_properties': missing, 'rule_cod': rule.cod},
            })
    return violations


def _eval_naming_convention(rule: BIMRule, definition: dict, scope: Optional[dict]) -> list[dict]:
    """Numele elementului trebuie sa respecte regex-ul dat."""
    selector = definition.get('selector', {})
    constraint = definition.get('constraint', {})
    pattern = constraint.get('name_regex')
    if not pattern:
        return []

    try:
        rgx = re.compile(pattern)
    except re.error as e:
        _logger.warning('Regex invalid in rule %s: %s', rule.cod, e)
        return [{'element_bim_id': None,
                 'mesaj': f'Regex invalid in regula {rule.cod}: {e}',
                 'detalii': {'rule_cod': rule.cod, 'eroare_config': True}}]

    violations = []
    for el in _select_elements(selector, scope):
        nume = el.nume or el.cod or ''
        if not rgx.match(nume):
            violations.append({
                'element_bim_id': el.id,
                'mesaj': f'{el.cod}: numele "{nume}" nu respecta conventia {pattern}',
                'detalii': {'rule_cod': rule.cod, 'pattern': pattern, 'name': nume},
            })
    return violations


def _eval_forbidden_in_zone(rule: BIMRule, definition: dict, scope: Optional[dict]) -> list[dict]:
    """
    Elementele selectate nu sunt permise in zone cu anumite categorii.
    Categoria zonei se ia din ElementBIM.spatiu.zona.tip (sau .categorie daca exista).
    """
    selector = definition.get('selector', {})
    constraint = definition.get('constraint', {})
    forbidden = set(constraint.get('zone_categories_forbidden', []))
    if not forbidden:
        return []

    violations = []
    for el in _select_elements(selector, scope):
        if not el.spatiu or not el.spatiu.zona:
            continue
        zona_categ = (getattr(el.spatiu.zona, 'tip_zona', None) or '').lower()
        if zona_categ and zona_categ in forbidden:
            violations.append({
                'element_bim_id': el.id,
                'spatiu_id': el.spatiu_id,
                'mesaj': f'{el.cod} ({el.tip_element}) interzis in zona "{zona_categ}"',
                'detalii': {'rule_cod': rule.cod, 'zone_category': zona_categ},
            })
    return violations


def _prag_clearance_m(constraint: dict) -> Optional[float]:
    """
    Extrage pragul de gabarit in METRI din constraint. Acceptam doua forme:
      - 'value_m'    -> deja in metri
      - 'distanta_mm'-> in milimetri (bbox-ul e in metri, deci impartim la 1000)
    Returneaza None daca nu e definit un prag valid (>0).
    """
    if constraint.get('value_m') is not None:
        try:
            v = float(constraint['value_m'])
            return v if v > 0 else None
        except (ValueError, TypeError):
            return None
    if constraint.get('distanta_mm') is not None:
        try:
            v = float(constraint['distanta_mm']) / 1000.0
            return v if v > 0 else None
        except (ValueError, TypeError):
            return None
    return None


def _eval_min_clearance(rule, definition, scope):
    """
    Gabarit minim intre elemente, evaluat geometric pe AABB (Faza 3).

    selector  : elementele "sursa" (ex. tubulatura).
    constraint:
        'min_distance_to' : tip_element tinta (ex. 'wall'). Optional - daca
                            lipseste, comparam sursa cu sursa.
        'value_m'         : prag in metri  (sau)
        'distanta_mm'     : prag in mm (bbox in metri -> /1000).

    Distanta AABB-AABB: gap_axa = max(a.min-b.max, b.min-a.max, 0);
    distanta = sqrt(sum(gap^2)). Daca distanta < prag -> violare.

    Folosim element.bbox (coordonate world, Faza 2). Daca un element nu are bbox,
    ramane 'neevaluat' ONEST pentru el (nu pass fals). Accelerare cu acelasi
    index spatial ca la clash, cu celulele dilatate cu pragul pentru a prinde
    perechile "aproape, nu suprapuse".
    """
    from services import clash_detection as clash_svc

    constraint = definition.get('constraint', {})
    selector = definition.get('selector', {})
    prag_m = _prag_clearance_m(constraint)
    if prag_m is None:
        return [{
            'mesaj': f'Regula {rule.cod}: prag de gabarit (value_m / distanta_mm) lipsa sau invalid.',
            'detalii': {'rule_cod': rule.cod, 'eroare_config': True},
        }]

    sursa = _select_elements(selector, scope)
    if not sursa:
        return []

    tip_tinta = constraint.get('min_distance_to')
    if tip_tinta:
        tinta_selector = {'tip_element': tip_tinta}
        # Pastram acelasi scope (santier) pentru tinta
        tinta = _select_elements(tinta_selector, scope)
    else:
        tinta = list(sursa)

    # Bbox-uri (din coloana Faza 2). Elementele fara bbox -> 'neevaluat' onest.
    def _bbox_map(els):
        out = {}
        fara = []
        for el in els:
            bb = clash_svc._get_bbox(el)
            if bb is None:
                fara.append(el)
            else:
                out[el.id] = (el, bb)
        return out, fara

    sursa_map, sursa_fara = _bbox_map(sursa)
    tinta_map, tinta_fara = _bbox_map(tinta)

    violations = []

    # Flag onest pentru elementele sursa fara geometrie (nu le declaram OK)
    for el in sursa_fara:
        violations.append({
            'element_bim_id': el.id,
            'mesaj': f'{el.cod}: gabarit neevaluat (lipseste bbox pe element).',
            'detalii': {'rule_cod': rule.cod, 'status': 'neevaluat_lipsa_bbox'},
        })

    if not sursa_map or not tinta_map:
        return violations

    # Index spatial pe tinta, cu celula >= prag ca sa prindem perechile apropiate.
    tinta_items = list(tinta_map.values())  # [(el, bb), ...]
    bboxes = [bb for _el, bb in tinta_items] + [bb for _el, bb in sursa_map.values()]
    cell_size = max(clash_svc._alege_cell_size(bboxes), prag_m, 0.25)

    grid: dict[tuple, list[int]] = {}
    for idx, (_el, bb) in enumerate(tinta_items):
        # Dilatam bbox-ul tinta cu pragul ca celulele candidate sa acopere
        # si vecinatatea (elemente la distanta < prag, nu doar suprapuse).
        bb_dilatat = {
            'min': [bb['min'][i] - prag_m for i in range(3)],
            'max': [bb['max'][i] + prag_m for i in range(3)],
        }
        for cheie in clash_svc._celule_atinse(bb_dilatat, cell_size):
            grid.setdefault(cheie, []).append(idx)

    raportate = set()  # (sursa_id, tinta_id) deja raportate
    for el_s, bb_s in sursa_map.values():
        candidati_idx = set()
        for cheie in clash_svc._celule_atinse(bb_s, cell_size):
            for idx in grid.get(cheie, ()):
                candidati_idx.add(idx)
        for idx in candidati_idx:
            el_t, bb_t = tinta_items[idx]
            if el_t.id == el_s.id:
                continue
            pereche = (el_s.id, el_t.id)
            if pereche in raportate:
                continue
            dist = clash_svc._aabb_distance(bb_s, bb_t)
            if dist < prag_m:
                raportate.add(pereche)
                violations.append({
                    'element_bim_id': el_s.id,
                    'mesaj': (f'{el_s.cod} ({el_s.tip_element}) la {round(dist, 4)}m de '
                              f'{el_t.cod} ({el_t.tip_element}) - sub gabaritul minim '
                              f'de {prag_m}m'),
                    'detalii': {'rule_cod': rule.cod, 'distanta_m': round(dist, 4),
                                'prag_m': prag_m, 'element_tinta_id': el_t.id},
                })

    return violations


# Mapping tip regula -> evaluator
EVALUATORS = {
    'required_properties': _eval_required_properties,
    'naming_convention': _eval_naming_convention,
    'forbidden_in_zone': _eval_forbidden_in_zone,
    'min_clearance': _eval_min_clearance,   # honest: flag "neevaluat", nu pass fals
}


# ====================================================
# ENGINE PRINCIPAL
# ====================================================

def run_rules(scope: Optional[dict] = None,
              rule_ids: Optional[list[int]] = None,
              user=None) -> dict:
    """
    Ruleaza toate regulile active (sau lista filtrata) si insereaza
    RuleViolation-uri in DB.

    Returneaza:
        {
            'run_id': '...',
            'total_rules': N,
            'total_violations': M,
            'by_severity': {'mica': ..., 'medie': ..., 'mare': ..., 'critica': ...},
            'rules_failed': [...]
        }
    """
    run_id = str(uuid.uuid4())
    started = datetime.utcnow()

    q = BIMRule.query.filter_by(activa=True)
    if rule_ids:
        q = q.filter(BIMRule.id.in_(rule_ids))
    rules = q.all()

    violations_data = []
    rules_with_errors = []

    for rule in rules:
        evaluator = EVALUATORS.get(rule.tip)
        if not evaluator:
            rules_with_errors.append({'rule_cod': rule.cod, 'eroare': f'tip {rule.tip} necunoscut'})
            continue
        try:
            definition = rule.get_definition()
            v_list = evaluator(rule, definition, scope) or []
            for v in v_list:
                v['rule_id'] = rule.id
                v['severitate'] = rule.severitate
                violations_data.append(v)
        except Exception as e:
            _logger.warning('Eroare la evaluarea regulii %s: %s', rule.cod, e, exc_info=False)
            rules_with_errors.append({'rule_cod': rule.cod, 'eroare': str(e)})

    # Persistent
    by_severity = {'mica': 0, 'medie': 0, 'mare': 0, 'critica': 0}
    for vd in violations_data:
        violation = RuleViolation(
            tenant_id=getattr(user, 'tenant_id', None) if user else None,
            rule_id=vd['rule_id'],
            element_bim_id=vd.get('element_bim_id'),
            spatiu_id=vd.get('spatiu_id'),
            run_id=run_id,
            mesaj=vd['mesaj'][:500],
            detalii_json=json.dumps(vd.get('detalii', {}), ensure_ascii=False),
            data_detectie=datetime.utcnow(),
            status='noua',
        )
        db.session.add(violation)
        sev = vd.get('severitate', 'medie')
        by_severity[sev] = by_severity.get(sev, 0) + 1

    db.session.commit()

    # Audit log run
    audit_svc.log(
        action='run_rules',
        entity_type='bim_rule_run',
        entity_id=None,
        new_values={
            'run_id': run_id,
            'total_rules': len(rules),
            'total_violations': len(violations_data),
            'by_severity': by_severity,
            'rules_with_errors': rules_with_errors,
            'duration_ms': int((datetime.utcnow() - started).total_seconds() * 1000),
        },
        commit=True,
    )

    return {
        'run_id': run_id,
        'total_rules': len(rules),
        'total_violations': len(violations_data),
        'by_severity': by_severity,
        'rules_failed': rules_with_errors,
        'duration_ms': int((datetime.utcnow() - started).total_seconds() * 1000),
    }


# ====================================================
# CRUD HELPERS
# ====================================================

def create_rule(cod: str, nume: str, tip: str, definition: dict,
                *, descriere: str = '', categorie: str = 'best_practice',
                severitate: str = 'medie', tenant_id: Optional[int] = None,
                user=None, commit: bool = True) -> BIMRule:
    """Creeaza o regula noua."""
    if tip not in EVALUATORS:
        raise ValueError(f'Tip regula necunoscut: {tip}')
    rule = BIMRule(
        tenant_id=tenant_id,
        cod=cod,
        nume=nume,
        descriere=descriere,
        categorie=categorie,
        severitate=severitate,
        tip=tip,
        definitie_json=json.dumps(definition, ensure_ascii=False),
        activa=True,
        creat_de_id=getattr(user, 'id', None) if user else None,
    )
    db.session.add(rule)
    db.session.flush()
    audit_svc.log_create('bim_rule', rule.id, new_values={'cod': cod, 'tip': tip})
    if commit:
        db.session.commit()
    return rule


def violation_to_issue(violation: RuleViolation, user) -> Optional[int]:
    """
    Converteste o violare in IssueBIM oficial. Returneaza issue.id.
    Doar admin/manager poate face conversia.
    """
    from models import IssueBIM
    if user.rol not in ('admin', 'manager'):
        raise PermissionError('Doar admin/manager poate confirma o violare ca issue.')
    if violation.issue_id:
        return violation.issue_id

    issue = IssueBIM(
        tenant_id=violation.tenant_id,
        tip='neconformitate',
        severitate=violation.rule.severitate,
        status='deschis',
        titlu=f'[{violation.rule.cod}] {violation.mesaj[:150]}',
        descriere=violation.mesaj,
        element_bim_id=violation.element_bim_id,
        spatiu_id=violation.spatiu_id,
        raportat_de_id=user.id,
    )
    db.session.add(issue)
    db.session.flush()

    violation.issue_id = issue.id
    violation.status = 'confirmata'
    db.session.commit()
    audit_svc.log('promote_violation_to_issue',
                  'bim_rule_violation', violation.id,
                  new_values={'issue_id': issue.id})
    return issue.id
