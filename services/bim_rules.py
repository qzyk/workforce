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


# Mapping tip regula -> evaluator
EVALUATORS = {
    'required_properties': _eval_required_properties,
    'naming_convention': _eval_naming_convention,
    'forbidden_in_zone': _eval_forbidden_in_zone,
    'min_clearance': lambda *a, **kw: [],  # placeholder Faza 4.1 (geometric)
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
