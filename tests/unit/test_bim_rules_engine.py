"""
Teste unit pentru rule engine (services.bim_rules).
"""

import json
import pytest

from models import (db, BIMRule, RuleViolation, ElementBIM, Spatiu, Zona,
                    Cladire, Santier, Nivel, Utilizator, IssueBIM)
from services import bim_rules


# ====================================================
# Fixtures helper
# ====================================================

@pytest.fixture
def admin(app):
    with app.app_context():
        u = Utilizator.query.filter_by(email='rules_admin@test.local').first()
        if not u:
            u = Utilizator(nume='RA', prenume='X', email='rules_admin@test.local',
                           rol='admin', activ=True)
            u.set_password('x'); db.session.add(u); db.session.commit()
        yield u


def _make_element(cladire_id, cod, tip='wall', proprietati=None, nume=None):
    el = ElementBIM(cladire_id=cladire_id, cod=cod,
                    tip_element=tip, status='proiectat',
                    nume=nume or cod,
                    proprietati_json=json.dumps(proprietati or {}))
    db.session.add(el)
    db.session.flush()
    return el


# ====================================================
# create_rule
# ====================================================

def test_create_rule_writes_audit(app, admin):
    with app.app_context():
        rule = bim_rules.create_rule(
            cod='RULE-T1', nume='Test required', tip='required_properties',
            definition={'selector': {'tip_element': 'wall'},
                        'constraint': {'required_properties': ['fire_rating']}},
            user=admin,
        )
        assert rule.id is not None
        assert rule.tip == 'required_properties'
        # Audit
        from models import AuditLog
        rows = AuditLog.query.filter_by(entity_type='bim_rule', action='create').count()
        assert rows >= 1


def test_create_rule_invalid_type_raises(app, admin):
    with app.app_context():
        with pytest.raises(ValueError):
            bim_rules.create_rule(
                cod='RULE-BAD', nume='X', tip='inexistent_type',
                definition={}, user=admin,
            )


# ====================================================
# required_properties evaluator
# ====================================================

def test_required_properties_finds_missing(app, admin):
    with app.app_context():
        s = Santier(cod='S-RP', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        # Element fara fire_rating
        _make_element(c.id, 'W001', tip='wall', proprietati={})
        # Element cu fire_rating
        _make_element(c.id, 'W002', tip='wall', proprietati={'fire_rating': 'EI60'})

        rule = bim_rules.create_rule(
            cod='RULE-RP1', nume='Pereti FR', tip='required_properties',
            definition={'selector': {'tip_element': 'wall'},
                        'constraint': {'required_properties': ['fire_rating']}},
            user=admin,
        )
        result = bim_rules.run_rules(user=admin)
        assert result['total_violations'] == 1
        v = RuleViolation.query.filter_by(rule_id=rule.id).first()
        assert 'fire_rating' in v.mesaj


def test_required_properties_skips_other_types(app, admin):
    with app.app_context():
        s = Santier(cod='S-OT', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        # Door (nu wall)
        _make_element(c.id, 'D001', tip='door', proprietati={})

        bim_rules.create_rule(
            cod='RULE-RP2', nume='Pereti only', tip='required_properties',
            definition={'selector': {'tip_element': 'wall'},
                        'constraint': {'required_properties': ['fire_rating']}},
            user=admin,
        )
        result = bim_rules.run_rules(user=admin)
        assert result['total_violations'] == 0


# ====================================================
# naming_convention evaluator
# ====================================================

def test_naming_convention_detects_invalid(app, admin):
    with app.app_context():
        s = Santier(cod='S-NM', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        _make_element(c.id, 'D001', tip='door', nume='USA-101')   # OK
        _make_element(c.id, 'D002', tip='door', nume='door-bad')  # FAIL

        bim_rules.create_rule(
            cod='RULE-NM1', nume='Door naming', tip='naming_convention',
            definition={'selector': {'tip_element': 'door'},
                        'constraint': {'name_regex': r'^USA-\d{3}$'}},
            user=admin,
        )
        result = bim_rules.run_rules(user=admin)
        assert result['total_violations'] == 1


def test_naming_invalid_regex_creates_config_error(app, admin):
    with app.app_context():
        s = Santier(cod='S-RX', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        _make_element(c.id, 'D001', tip='door')
        bim_rules.create_rule(
            cod='RULE-NMBAD', nume='Bad regex', tip='naming_convention',
            definition={'selector': {'tip_element': 'door'},
                        'constraint': {'name_regex': '['}},  # invalid
            user=admin,
        )
        result = bim_rules.run_rules(user=admin)
        # 1 violation reportata cu eroare de configuratie
        assert result['total_violations'] >= 1


# ====================================================
# forbidden_in_zone evaluator
# ====================================================

def test_forbidden_in_zone(app, admin):
    with app.app_context():
        s = Santier(cod='S-FZ', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        n = Nivel(cladire_id=c.id, cod='N1', nume='Et1', elevatie_m=0); db.session.add(n); db.session.flush()
        z_wet = Zona(cladire_id=c.id, nivel_id=n.id, cod='Z-WET', nume='Baie', tip_zona='wet')
        db.session.add(z_wet); db.session.flush()
        sp = Spatiu(zona_id=z_wet.id, nivel_id=n.id, cod='SP-1', nume='Baie 1', tip_spatiu='room')
        db.session.add(sp); db.session.flush()

        # Panou electric in baie - NU permis
        _make_element(c.id, 'P001', tip='panel')
        el = ElementBIM.query.filter_by(cod='P001').first()
        el.spatiu_id = sp.id
        db.session.commit()

        bim_rules.create_rule(
            cod='RULE-FZ1', nume='Panouri nu in wet', tip='forbidden_in_zone',
            definition={'selector': {'tip_element': 'panel'},
                        'constraint': {'zone_categories_forbidden': ['wet']}},
            user=admin,
        )
        result = bim_rules.run_rules(user=admin)
        assert result['total_violations'] == 1


# ====================================================
# violation_to_issue
# ====================================================

def test_violation_to_issue_admin_only(app, admin):
    with app.app_context():
        s = Santier(cod='S-V2I', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        _make_element(c.id, 'W001', tip='wall', proprietati={})
        rule = bim_rules.create_rule(
            cod='RULE-V2I', nume='X', tip='required_properties',
            definition={'selector': {'tip_element': 'wall'},
                        'constraint': {'required_properties': ['x']}},
            user=admin,
        )
        bim_rules.run_rules(user=admin)
        v = RuleViolation.query.filter_by(rule_id=rule.id).first()

        # Operator: respins
        op = Utilizator(nume='Op', prenume='X', email='v2i_op@test.local',
                        rol='operator', activ=True)
        op.set_password('x'); db.session.add(op); db.session.commit()
        with pytest.raises(PermissionError):
            bim_rules.violation_to_issue(v, op)

        # Admin: success
        issue_id = bim_rules.violation_to_issue(v, admin)
        assert issue_id is not None
        v_after = RuleViolation.query.get(v.id)
        assert v_after.issue_id == issue_id
        assert v_after.status == 'confirmata'
        issue = IssueBIM.query.get(issue_id)
        assert issue.tip == 'neconformitate'


# ====================================================
# Scope filter (santier_id)
# ====================================================

def test_scope_limits_to_santier(app, admin):
    with app.app_context():
        s1 = Santier(cod='S-A', nume='A'); db.session.add(s1)
        s2 = Santier(cod='S-B', nume='B'); db.session.add(s2)
        db.session.flush()
        c1 = Cladire(santier_id=s1.id, cod='C1', nume='X'); db.session.add(c1)
        c2 = Cladire(santier_id=s2.id, cod='C2', nume='Y'); db.session.add(c2)
        db.session.flush()
        _make_element(c1.id, 'W-A', tip='wall', proprietati={})
        _make_element(c2.id, 'W-B', tip='wall', proprietati={})

        bim_rules.create_rule(
            cod='RULE-SC', nume='X', tip='required_properties',
            definition={'selector': {'tip_element': 'wall'},
                        'constraint': {'required_properties': ['fire_rating']}},
            user=admin,
        )
        # Scope la S-A: 1 violare (W-A); fara scope: 2
        r_scoped = bim_rules.run_rules(scope={'santier_id': s1.id}, user=admin)
        # NOTA: violarile precedente raman in DB; comparam doar acest run
        run_id = r_scoped['run_id']
        scoped_count = RuleViolation.query.filter_by(run_id=run_id).count()
        assert scoped_count == 1
