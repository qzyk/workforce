"""
Integration tests pentru rutele Faza 4 (rules + clash).
"""

import json
import pytest

from models import (db, BIMRule, ClashRun, ClashGroup, Santier, Cladire,
                    ElementBIM, IssueBIM)
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


# ============================================================
# Faza 3: clash group status + promote-to-issue + matrice + delta
# ============================================================

def _seed_clash_group(app):
    """Creeaza un santier cu 2 elemente care se intersecteaza + ruleaza clash
    geometric -> returneaza (santier_id, group_id, run_id)."""
    from services import clash_detection
    from models import Utilizator
    with app.app_context():
        ff.set_flag('bim-clash-detection', True)
        u = Utilizator.query.filter_by(email='admin_test@test.local').first()
        s = Santier(cod='S-CG', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        for cod, mn, mx in [('E1', [0, 0, 0], [2, 2, 2]), ('E2', [1, 1, 1], [3, 3, 3])]:
            db.session.add(ElementBIM(cladire_id=c.id, cod=cod, tip_element='wall',
                                      status='proiectat', nume=cod,
                                      bbox_json=json.dumps({'min': mn, 'max': mx})))
        db.session.commit()
        res = clash_detection.run_clash_detection(santier_id=s.id, tip='geometric', user=u)
        g = ClashGroup.query.first()
        return s.id, g.id, res['run_id']


def test_clash_group_status_route(authenticated_client, app):
    _sid, gid, _rid = _seed_clash_group(app)
    resp = authenticated_client.post(f'/bim/clash/group/{gid}/status',
                                     data={'status': 'rezolvat'},
                                     follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        assert ClashGroup.query.get(gid).status == 'rezolvat'


def test_clash_group_status_invalid_rejected(authenticated_client, app):
    _sid, gid, _rid = _seed_clash_group(app)
    resp = authenticated_client.post(f'/bim/clash/group/{gid}/status',
                                     data={'status': 'aiurea'},
                                     follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        assert ClashGroup.query.get(gid).status == 'activ'  # neschimbat


def test_clash_group_promote_to_issue_route(authenticated_client, app):
    _sid, gid, _rid = _seed_clash_group(app)
    resp = authenticated_client.post(f'/bim/clash/group/{gid}/promote-to-issue',
                                     follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        g = ClashGroup.query.get(gid)
        assert g.issue_id is not None
        assert IssueBIM.query.get(g.issue_id) is not None


def test_clash_matrice_route(authenticated_client, app):
    _sid, _gid, rid = _seed_clash_group(app)
    resp = authenticated_client.get(f'/bim/clash/{rid}/matrice')
    assert resp.status_code == 200
    assert b'Matrice' in resp.data


def test_clash_status_route_flag_off_redirects(authenticated_client, app):
    _sid, gid, _rid = _seed_clash_group(app)
    with app.app_context():
        ff.set_flag('bim-clash-detection', False)
    resp = authenticated_client.post(f'/bim/clash/group/{gid}/status',
                                     data={'status': 'rezolvat'},
                                     follow_redirects=False)
    assert resp.status_code == 302  # gate flag -> redirect la dashboard
    with app.app_context():
        # Cu flag OFF actiunea nu se aplica (status neschimbat)
        assert ClashGroup.query.get(gid).status == 'activ'
