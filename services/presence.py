"""
Presence service: heartbeat user pentru afisare "cine e online".

UPSERT pe (user_id) - 1 row per user, refresh la fiecare heartbeat.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from models import db, UserPresence


_logger = logging.getLogger(__name__)


PRESENCE_TIMEOUT_SECONDS = 90  # cat ramane "online" fara heartbeat


def heartbeat(user_id: int, *,
              user_nume: Optional[str] = None,
              context_type: Optional[str] = None,
              context_id: Optional[int] = None,
              tenant_id: Optional[int] = None,
              commit: bool = True) -> UserPresence:
    """UPSERT presence pentru un user."""
    presence = UserPresence.query.filter_by(user_id=user_id).first()
    now = datetime.utcnow()
    if presence is None:
        presence = UserPresence(
            tenant_id=tenant_id,
            user_id=user_id,
            user_nume=user_nume,
            context_type=context_type,
            context_id=context_id,
            last_seen_at=now,
        )
        db.session.add(presence)
    else:
        presence.last_seen_at = now
        if user_nume:
            presence.user_nume = user_nume
        if context_type:
            presence.context_type = context_type
        presence.context_id = context_id  # poate fi None

    if commit:
        db.session.commit()
    return presence


def get_active_users(*, context_type: Optional[str] = None,
                     context_id: Optional[int] = None,
                     tenant_id: Optional[int] = None) -> list[UserPresence]:
    """
    Returneaza user-ii cu heartbeat in ultimele PRESENCE_TIMEOUT_SECONDS.
    Optional filtrat pe context (ex: cine e pe kanban santier 5).
    """
    cutoff = datetime.utcnow() - timedelta(seconds=PRESENCE_TIMEOUT_SECONDS)
    q = UserPresence.query.filter(UserPresence.last_seen_at >= cutoff)
    if context_type:
        q = q.filter_by(context_type=context_type)
    if context_id is not None:
        q = q.filter_by(context_id=context_id)
    if tenant_id is not None:
        q = q.filter_by(tenant_id=tenant_id)
    return q.order_by(UserPresence.last_seen_at.desc()).all()


def cleanup_stale_presence(older_than_minutes: int = 60) -> int:
    """Sterge presence rows mai vechi de X minute."""
    cutoff = datetime.utcnow() - timedelta(minutes=older_than_minutes)
    deleted = UserPresence.query.filter(UserPresence.last_seen_at < cutoff).delete()
    db.session.commit()
    return deleted
