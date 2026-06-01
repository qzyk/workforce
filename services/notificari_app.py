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

from models import db, NotificareApp


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
        tenant_id=tenant_id,
        citita=False,
    )
    db.session.add(n)
    db.session.flush()
    return n


def marcheaza_citita(notificare_id: int, utilizator_id: int) -> bool:
    """Marcheaza o notificare ca citita. Returneaza True daca a actualizat."""
    n = NotificareApp.query.filter_by(
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
    necitite = NotificareApp.query.filter_by(
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
        return NotificareApp.query.filter_by(
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
    q = NotificareApp.query.filter_by(utilizator_id=utilizator_id)
    if doar_necitite:
        q = q.filter_by(citita=False)
    return q.order_by(NotificareApp.data_creare.desc()).limit(limit).all()
