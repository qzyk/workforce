"""
Integration tests pentru rutele Faza 4 (rules + clash).
"""

import json
import pytest

from models import db, BIMRule, ClashRun, Santier
from services import feature_flags as ff


def test_rules_lista_redirects_when_flag_off(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-rule-engine', False)
    resp = authenticated_client.get('/bim/rules', follow_redirects=False)
    assert resp.status_code == 302


def test_rules_lista_renders_when_flag_on(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-rule-engine', True)
    resp = authenticated_client.get('/bim/rules')
    assert resp.status_code == 200
    assert b'Reguli' in resp.data or b'reguli' in resp.data


def test_violations_lista_renders_when_flag_on(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-rule-engine', True)
    resp = authenticated_client.get('/bim/violations')
    assert resp.status_code == 200


def test_clash_lista_renders_when_flag_on(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-clash-detection', True)
    resp = authenticated_client.get('/bim/clash')
    assert resp.status_code == 200


def test_clash_run_requires_scope(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-clash-detection', True)
    resp = authenticated_client.post('/bim/clash/run', data={'tip': 'mixed'},
                                     follow_redirects=False)
    assert resp.status_code == 302  # redirect cu flash error


def test_clash_run_creates_run_and_redirects_to_detail(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-clash-detection', True)
        ClashRun.query.delete()
        s = Santier(cod='S-INT', nume='X')
        db.session.add(s)
        db.session.commit()
        sid = s.id

    resp = authenticated_client.post('/bim/clash/run',
                                     data={'santier_id': sid, 'tip': 'logic'},
                                     follow_redirects=False)
    assert resp.status_code == 302
    assert '/clash/' in resp.headers.get('Location', '')

    with app.app_context():
        runs = ClashRun.query.filter_by(santier_id=sid).all()
        assert len(runs) == 1
        assert runs[0].status == 'finalizat'


def test_api_clash_returns_disabled_when_flag_off(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-clash-detection', False)
        s = Santier(cod='S-API-OFF', nume='X')
        db.session.add(s)
        db.session.commit()
        # Create a run manually
        run = ClashRun(santier_id=s.id, tip='logic', status='finalizat')
        db.session.add(run)
        db.session.commit()
        run_id = run.id

    resp = authenticated_client.get(f'/bim/api/clash/{run_id}')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['enabled'] is False


def test_create_rule_via_route(authenticated_client, app):
    """Admin creeaza o regula prin formular -> in DB + audit."""
    from models import AuditLog
    with app.app_context():
        ff.set_flag('bim-rule-engine', True)
        BIMRule.query.delete()
        AuditLog.query.delete()
        db.session.commit()

    resp = authenticated_client.post('/bim/rule/nou', data={
        'cod': 'RULE-INT-1', 'nume': 'Test int', 'tip': 'required_properties',
        'definitie_json': json.dumps({
            'selector': {'tip_element': 'wall'},
            'constraint': {'required_properties': ['fire_rating']},
        }),
        'categorie': 'safety', 'severitate': 'mare',
    }, follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        r = BIMRule.query.filter_by(cod='RULE-INT-1').first()
        assert r is not None
        assert r.tip == 'required_properties'
