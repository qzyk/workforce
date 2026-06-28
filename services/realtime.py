"""
Real-time event service pentru SSE streaming.

Publica evenimente in tabel bim_realtime_events. Consumatorii (clientii SSE)
fac long-polling pe acest tabel cu cursor 'since=<event_id>'.

Pe PythonAnywhere (fara WebSockets persistente) - SSE prin uwsgi merge nativ.
Stream se inchide la 30s; clientul reconnecteaza cu since=<last_id>.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

from models import db, RealtimeEvent
from services.security.tenant_access import (
    get_current_tenant_id_safe,
    query_realtime_events_for_tenant,
)


_logger = logging.getLogger(__name__)


# ====================================================
# PUBLISH
# ====================================================

def publish_event(event_type: str, *,
                  santier_id: Optional[int] = None,
                  proiect_id: Optional[int] = None,
                  payload: Optional[dict] = None,
                  user_id: Optional[int] = None,
                  tenant_id: Optional[int] = None,
                  commit: bool = True) -> RealtimeEvent:
    """
    Publica un eveniment in stream. Returneaza event-ul creat.

    event_type:
        issue_status_change | comment_new | sensor_alert |
        presence_join | presence_leave | model_version_changed
    """
    tenant_event = tenant_id if tenant_id is not None else get_current_tenant_id_safe()
    event = RealtimeEvent(
        tenant_id=tenant_event,
        santier_id=santier_id,
        proiect_id=proiect_id,
        event_type=event_type,
        payload_json=json.dumps(payload, ensure_ascii=False, default=str) if payload else None,
        user_id=user_id,
        created_at=datetime.utcnow(),
    )
    db.session.add(event)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return event


# ====================================================
# CONSUME (SSE long-polling)
# ====================================================

def get_events_since(event_id: int, *,
                     santier_id: Optional[int] = None,
                     proiect_id: Optional[int] = None,
                     tenant_id: Optional[int] = None,
                     limit: int = 100) -> list[RealtimeEvent]:
    """
    Returneaza evenimentele cu id > event_id, filtrate pe scope.
    """
    q = query_realtime_events_for_tenant(tenant_id=tenant_id).filter(RealtimeEvent.id > event_id)
    if santier_id is not None:
        q = q.filter(RealtimeEvent.santier_id == santier_id)
    if proiect_id is not None:
        q = q.filter(RealtimeEvent.proiect_id == proiect_id)
    return q.order_by(RealtimeEvent.id).limit(limit).all()


def get_latest_event_id(tenant_id: Optional[int] = None) -> int:
    """Returneaza id-ul ultimului eveniment (sau 0 daca tabel gol)."""
    last = query_realtime_events_for_tenant(tenant_id=tenant_id).order_by(
        RealtimeEvent.id.desc()
    ).first()
    return last.id if last else 0


def serialize_event(event: RealtimeEvent) -> dict:
    """Format pentru SSE data field."""
    return {
        'id': event.id,
        'type': event.event_type,
        'santier_id': event.santier_id,
        'proiect_id': event.proiect_id,
        'user_id': event.user_id,
        'created_at': event.created_at.isoformat() if event.created_at else None,
        'payload': json.loads(event.payload_json) if event.payload_json else {},
    }


def cleanup_old_events(older_than_days: int = 7) -> int:
    """Sterge evenimentele mai vechi de X zile. Returneaza nr randuri sterse."""
    cutoff = datetime.utcnow() - timedelta(days=older_than_days)
    deleted = RealtimeEvent.query.filter(RealtimeEvent.created_at < cutoff).delete()
    db.session.commit()
    return deleted


# ====================================================
# Helper: stream generator (folosit de route SSE)
# ====================================================

def sse_stream(santier_id: Optional[int], proiect_id: Optional[int],
               start_after_id: int = 0,
               max_duration_seconds: int = 30,
               poll_interval_seconds: float = 2.0,
               tenant_id: Optional[int] = None):
    """
    Generator pentru SSE stream. Yield evenimente noi pe parcursul
    max_duration_seconds. Format SSE: 'data: <json>\\n\\n'.

    NOTA: foloseste un app context curent (apelat din route Flask).
    """
    cursor = start_after_id
    start_time = time.monotonic()

    # Hello initial - confirma conexiunea
    yield f': connected, cursor={cursor}\n\n'

    while True:
        if (time.monotonic() - start_time) > max_duration_seconds:
            # Inchidem stream-ul cu un mesaj final ca sa stie clientul sa reconnecteze
            yield 'event: close\ndata: {"reason": "max_duration"}\n\n'
            return

        try:
            events = get_events_since(cursor, santier_id=santier_id,
                                       proiect_id=proiect_id,
                                       tenant_id=tenant_id, limit=50)
        except Exception as e:
            _logger.warning('sse_stream get_events error: %s', e)
            yield f'event: error\ndata: {{"error": "{e}"}}\n\n'
            return

        if events:
            for ev in events:
                payload = json.dumps(serialize_event(ev), ensure_ascii=False, default=str)
                yield f'event: {ev.event_type}\ndata: {payload}\nid: {ev.id}\n\n'
                cursor = ev.id
        else:
            # Keepalive comment pentru a nu inchide socket-ul
            yield ': keepalive\n\n'

        time.sleep(poll_interval_seconds)
