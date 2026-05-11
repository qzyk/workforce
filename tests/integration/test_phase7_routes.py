"""
Integration tests pentru rutele Faza 7 (Kanban + Comments + Presence + SSE).
"""

import json
import pytest

from models import (db, IssueBIM, BIMComment, UserPresence, RealtimeEvent,
                    ElementBIM, Cladire, Santier)
from services import feature_flags as ff


@pytest.fixture
def issue(app):
    with app.app_context():
        s = Santier(cod='S-INT7', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        el = ElementBIM(cladire_id=c.id, cod='E1', tip_element='wall',
                        status='construit', nume='W')
        db.session.add(el); db.session.flush()
        iss = IssueBIM(titlu='Test issue', tip='defect',
                       severitate='medie', status='deschis',
                       element_bim_id=el.id, cladire_id=c.id)
        db.session.add(iss); db.session.commit()
        yield {'issue_id': iss.id, 'santier_id': s.id, 'cladire_id': c.id, 'el_id': el.id}


# ====================================================
# KANBAN
# ====================================================

def test_kanban_redirects_when_flag_off(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-issue-kanban', False)
    resp = authenticated_client.get('/bim/kanban', follow_redirects=False)
    assert resp.status_code == 302


def test_kanban_renders_when_flag_on(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-issue-kanban', True)
    resp = authenticated_client.get('/bim/kanban')
    assert resp.status_code == 200
    assert b'Kanban' in resp.data or b'kanban' in resp.data


def test_kanban_filters_by_santier(authenticated_client, app, issue):
    with app.app_context():
        ff.set_flag('bim-issue-kanban', True)
    resp = authenticated_client.get(f'/bim/kanban/santier/{issue["santier_id"]}')
    assert resp.status_code == 200
    # Issue-ul de test e in HTML
    assert b'Test issue' in resp.data


def test_issue_change_status_via_post(authenticated_client, app, issue):
    """Drag & drop kanban -> POST status change."""
    with app.app_context():
        ff.set_flag('bim-realtime-collab', True)
        ff.set_flag('bim-issue-kanban', True)
        RealtimeEvent.query.delete()
        db.session.commit()

    resp = authenticated_client.post(
        f'/bim/issue/{issue["issue_id"]}/status',
        data={'status': 'in_lucru'},
        headers={'Accept': 'application/json'},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is True

    with app.app_context():
        iss = IssueBIM.query.get(issue['issue_id'])
        assert iss.status == 'in_lucru'
        # Eveniment publicat
        evs = RealtimeEvent.query.filter_by(event_type='issue_status_change').all()
        assert len(evs) == 1


def test_issue_change_status_invalid(authenticated_client, app, issue):
    resp = authenticated_client.post(
        f'/bim/issue/{issue["issue_id"]}/status',
        data={'status': 'INVALID'},
        headers={'Accept': 'application/json'},
    )
    assert resp.status_code == 400


def test_operator_cannot_close(operator_client, app, issue):
    """Operator nu poate inchide issue (doar admin/manager)."""
    with app.app_context():
        ff.set_flag('bim-issue-kanban', True)
    resp = operator_client.post(
        f'/bim/issue/{issue["issue_id"]}/status',
        data={'status': 'inchis'},
        headers={'Accept': 'application/json'},
    )
    assert resp.status_code == 403


# ====================================================
# COMMENTS
# ====================================================

def test_comments_lista_renders(authenticated_client, app, issue):
    resp = authenticated_client.get(f'/bim/issue/{issue["issue_id"]}/comments')
    assert resp.status_code == 200


def test_create_comment(authenticated_client, app, issue):
    with app.app_context():
        ff.set_flag('bim-realtime-collab', True)
        BIMComment.query.delete()
        db.session.commit()

    resp = authenticated_client.post(
        f'/bim/issue/{issue["issue_id"]}/comments',
        data={'text': 'Acesta e un comentariu de test.'},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302)

    with app.app_context():
        comments = BIMComment.query.filter_by(issue_id=issue['issue_id']).all()
        assert len(comments) == 1
        assert 'comentariu de test' in comments[0].text


def test_create_comment_empty_rejected(authenticated_client, app, issue):
    with app.app_context():
        ff.set_flag('bim-realtime-collab', True)
    resp = authenticated_client.post(
        f'/bim/issue/{issue["issue_id"]}/comments',
        json={'text': ''},
    )
    # Returns 400 sau 415 depending on json/form
    assert resp.status_code in (400, 415)


def test_create_comment_publishes_event(authenticated_client, app, issue):
    with app.app_context():
        ff.set_flag('bim-realtime-collab', True)
        RealtimeEvent.query.delete()
        db.session.commit()

    authenticated_client.post(
        f'/bim/issue/{issue["issue_id"]}/comments',
        data={'text': 'Test comment for event'},
    )
    with app.app_context():
        evs = RealtimeEvent.query.filter_by(event_type='comment_new').all()
        assert len(evs) == 1


def test_api_issue_comments_returns_json(authenticated_client, app, issue, admin_user):
    with app.app_context():
        ff.set_flag('bim-realtime-collab', True)
        c = BIMComment(issue_id=issue['issue_id'], autor_id=admin_user.id,
                       text='Comm 1')
        db.session.add(c); db.session.commit()
    resp = authenticated_client.get(f'/bim/api/issue/{issue["issue_id"]}/comments')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['count'] >= 1


# ====================================================
# PRESENCE
# ====================================================

def test_heartbeat_endpoint_writes_row(authenticated_client, app, admin_user):
    with app.app_context():
        ff.set_flag('bim-realtime-collab', True)
        UserPresence.query.delete()
        db.session.commit()

    resp = authenticated_client.post(
        '/bim/api/presence/heartbeat',
        data={'context_type': 'kanban', 'context_id': '5'},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is True

    with app.app_context():
        p = UserPresence.query.filter_by(user_id=admin_user.id).first()
        assert p is not None
        assert p.context_type == 'kanban'
        assert p.context_id == 5


def test_heartbeat_disabled_when_flag_off(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-realtime-collab', False)
    resp = authenticated_client.post('/bim/api/presence/heartbeat', data={})
    data = resp.get_json()
    assert data['enabled'] is False


# ====================================================
# SSE STREAM
# ====================================================

def test_sse_stream_disabled_returns_403(authenticated_client, app):
    with app.app_context():
        ff.set_flag('bim-realtime-collab', False)
    resp = authenticated_client.get('/bim/api/events/stream')
    assert resp.status_code == 403


def test_sse_stream_returns_event_stream_content_type(authenticated_client, app):
    """Quick check: stream returns text/event-stream. Don't actually consume."""
    with app.app_context():
        ff.set_flag('bim-realtime-collab', True)
    # Folosim test_client.get cu buffered=True ar bloca; in schimb facem HEAD-like
    # check headers prin parametri shortcut
    resp = authenticated_client.get('/bim/api/events/stream', buffered=False)
    # Close conection immediately
    assert resp.status_code == 200
    assert 'text/event-stream' in resp.headers.get('Content-Type', '')
    resp.close()
