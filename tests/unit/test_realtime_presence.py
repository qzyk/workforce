"""
Teste unit pentru services.realtime + services.presence.
"""

from datetime import datetime, timedelta
import json
import pytest

from models import db, RealtimeEvent, UserPresence, Utilizator
from services import realtime, presence


@pytest.fixture
def user(app):
    with app.app_context():
        u = Utilizator.query.filter_by(email='rt_user@test.local').first()
        if not u:
            u = Utilizator(nume='RT', prenume='X', email='rt_user@test.local',
                           rol='operator', activ=True)
            u.set_password('x'); db.session.add(u); db.session.commit()
        yield u


# ====================================================
# REALTIME
# ====================================================

def test_publish_event_creates_row(app):
    with app.app_context():
        ev = realtime.publish_event('issue_status_change',
                                     santier_id=1,
                                     payload={'issue_id': 42, 'old': 'deschis', 'new': 'in_lucru'})
        assert ev.id is not None
        assert ev.event_type == 'issue_status_change'
        payload = json.loads(ev.payload_json)
        assert payload['issue_id'] == 42


def test_get_events_since_returns_new_only(app):
    with app.app_context():
        e1 = realtime.publish_event('comment_new', santier_id=1, payload={'a': 1})
        e2 = realtime.publish_event('comment_new', santier_id=1, payload={'a': 2})
        e3 = realtime.publish_event('comment_new', santier_id=2, payload={'a': 3})
        # Since e1 -> [e2, e3] sau filtru pe santier_id=1 -> [e2]
        events = realtime.get_events_since(e1.id, santier_id=1)
        assert len(events) == 1
        assert events[0].id == e2.id


def test_get_latest_event_id(app):
    with app.app_context():
        RealtimeEvent.query.delete(); db.session.commit()
        assert realtime.get_latest_event_id() == 0
        e = realtime.publish_event('comment_new', santier_id=1, payload={})
        assert realtime.get_latest_event_id() == e.id


def test_serialize_event(app):
    with app.app_context():
        ev = realtime.publish_event('comment_new', santier_id=5,
                                     payload={'x': 1}, user_id=10)
        ser = realtime.serialize_event(ev)
        assert ser['id'] == ev.id
        assert ser['type'] == 'comment_new'
        assert ser['santier_id'] == 5
        assert ser['user_id'] == 10
        assert ser['payload'] == {'x': 1}


def test_cleanup_old_events(app):
    with app.app_context():
        RealtimeEvent.query.delete(); db.session.commit()
        # Old event manual
        old = RealtimeEvent(event_type='x',
                             created_at=datetime.utcnow() - timedelta(days=30))
        db.session.add(old)
        # Recent
        realtime.publish_event('x', payload={})
        db.session.commit()

        deleted = realtime.cleanup_old_events(older_than_days=7)
        assert deleted == 1
        assert RealtimeEvent.query.count() == 1


# ====================================================
# PRESENCE
# ====================================================

def test_heartbeat_creates_row(app, user):
    with app.app_context():
        p = presence.heartbeat(user.id, user_nume='Test User',
                                context_type='kanban', context_id=5)
        assert p.id is not None
        assert p.user_nume == 'Test User'
        assert p.context_type == 'kanban'
        assert p.context_id == 5


def test_heartbeat_updates_existing(app, user):
    with app.app_context():
        p1 = presence.heartbeat(user.id, context_type='kanban', context_id=5)
        first_seen = p1.last_seen_at
        import time
        time.sleep(0.01)
        p2 = presence.heartbeat(user.id, context_type='kanban', context_id=5)
        assert p2.id == p1.id
        assert p2.last_seen_at > first_seen


def test_get_active_users_filter_by_context(app, user):
    with app.app_context():
        UserPresence.query.delete(); db.session.commit()
        # User pe kanban santier 5
        presence.heartbeat(user.id, user_nume='X',
                            context_type='kanban', context_id=5)
        # Alt user pe viewer
        u2 = Utilizator(nume='Y', prenume='Z', email='rt2@test.local',
                         rol='operator', activ=True)
        u2.set_password('x'); db.session.add(u2); db.session.commit()
        presence.heartbeat(u2.id, user_nume='Y',
                            context_type='viewer_federat', context_id=5)

        active_kanban = presence.get_active_users(context_type='kanban', context_id=5)
        assert len(active_kanban) == 1
        assert active_kanban[0].user_id == user.id


def test_cleanup_stale_presence(app, user):
    with app.app_context():
        UserPresence.query.delete(); db.session.commit()
        # Stale
        old = UserPresence(user_id=user.id,
                            last_seen_at=datetime.utcnow() - timedelta(hours=2))
        db.session.add(old); db.session.commit()
        deleted = presence.cleanup_stale_presence(older_than_minutes=60)
        assert deleted == 1
