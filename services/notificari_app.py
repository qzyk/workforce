"""
Helper-i pentru gestionarea NotificareApp (Faza 14).

Functii publice:
  - creeaza_notificare(utilizator_id, tip, titlu, mesaj, ...) -> NotificareApp
    Idempotent prin (utilizator_id, tip, entitate_referinta, id_entitate, day):
    NU se duplica notificare pentru aceeasi sursa in aceeasi zi.
  - marcheaza_citita(notificare_id, utilizator_id) -> bool
  - marcheaza_toate_citite(utilizator_id) -> int (count)
  - count_necitite(utilizator_id) -> int
  - lista_notificari(utilizator_id, doar_necitite=False, limit=100) -> list
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from models import db, NotificareApp, Utilizator
from services.security.tenant_access import (
    get_tenant_mode,
    query_notifications_for_tenant,
)
from tenant import MODE_OFF


def creeaza_notificare(
    utilizator_id: int,
    tip: str,
    titlu: str,
    mesaj: Optional[str] = None,
    link_url: Optional[str] = None,
    entitate_referinta: Optional[str] = None,
    id_entitate_referinta: Optional[int] = None,
    tenant_id: Optional[int] = None,
    skip_duplicate_today: bool = True,
) -> Optional[NotificareApp]:
    """
    Creeaza o NotificareApp pentru un utilizator.

    Daca skip_duplicate_today=True, verifica idempotenta: nu duplica
    notificare cu acelasi (utilizator, tip, entitate_referinta,
    id_entitate_referinta) creata azi.

    Returneaza NotificareApp creat sau (None daca skipped duplicate).
    """
    tenant_notificare = _tenant_id_notificare_pentru_destinatar(
        utilizator_id,
        tenant_id,
    )
    if tenant_notificare is False:
        return None

    if skip_duplicate_today and entitate_referinta and id_entitate_referinta:
        # fereastra de azi pe acelasi ceas ca `data_creare` (UTC) - altfel, in
        # fusurile UTC+N, inainte de pranz UTC fereastra (miezul noptii local)
        # excludea inregistrarile UTC si idempotenta esua (notificari duplicate).
        today_start = datetime.combine(datetime.utcnow().date(), datetime.min.time())
        existing = NotificareApp.query.filter(
            NotificareApp.utilizator_id == utilizator_id,
            NotificareApp.tip == tip,
            NotificareApp.entitate_referinta == entitate_referinta,
            NotificareApp.id_entitate_referinta == id_entitate_referinta,
            NotificareApp.data_creare >= today_start,
        ).first()
        if existing is not None:
            return None

    n = NotificareApp(
        utilizator_id=utilizator_id,
        tip=tip,
        titlu=titlu,
        mesaj=mesaj,
        link_url=link_url,
        entitate_referinta=entitate_referinta,
        id_entitate_referinta=id_entitate_referinta,
        tenant_id=tenant_notificare,
        citita=False,
    )
    db.session.add(n)
    db.session.flush()
    return n


def marcheaza_citita(notificare_id: int, utilizator_id: int) -> bool:
    """Marcheaza o notificare ca citita. Returneaza True daca a actualizat."""
    n = query_notifications_for_tenant().filter_by(
        id=notificare_id, utilizator_id=utilizator_id
    ).first()
    if n is None:
        return False
    if n.citita:
        return False
    n.citita = True
    n.data_citire = datetime.utcnow()
    db.session.commit()
    return True


def marcheaza_toate_citite(utilizator_id: int) -> int:
    """Bulk mark-as-read pentru un utilizator. Returneaza count actualizat."""
    necitite = query_notifications_for_tenant().filter_by(
        utilizator_id=utilizator_id, citita=False
    ).all()
    now = datetime.utcnow()
    for n in necitite:
        n.citita = True
        n.data_citire = now
    db.session.commit()
    return len(necitite)


def count_necitite(utilizator_id: int) -> int:
    """Numara notificarile necitite (folosit pentru bell badge)."""
    try:
        return query_notifications_for_tenant().filter_by(
            utilizator_id=utilizator_id, citita=False
        ).count()
    except Exception:
        # Daca DB nu e gata sau tabel lipsa -> 0
        return 0


def lista_notificari(
    utilizator_id: int,
    doar_necitite: bool = False,
    limit: int = 100,
) -> list[NotificareApp]:
    """Lista notificari pentru un utilizator, sortate descrescator dupa data."""
    q = query_notifications_for_tenant().filter_by(utilizator_id=utilizator_id)
    if doar_necitite:
        q = q.filter_by(citita=False)
    return q.order_by(NotificareApp.data_creare.desc()).limit(limit).all()


def _tenant_id_notificare_pentru_destinatar(utilizator_id: int, tenant_id):
    """Returneaza tenant_id sigur pentru notificare sau False daca e mix strain."""
    if get_tenant_mode() == MODE_OFF:
        return tenant_id

    user = db.session.get(Utilizator, utilizator_id)
    user_tenant_id = getattr(user, 'tenant_id', None) if user else None

    if tenant_id is not None and user_tenant_id is not None and int(tenant_id) != int(user_tenant_id):
        return False
    if tenant_id is None:
        return user_tenant_id
    return tenant_id
