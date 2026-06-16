"""
Serviciu pentru modulul Concedii (gestiune absente).

Functii pure, fara dependente de request, usor de testat:
- calcul_zile_lucratoare: numara zilele lucratoare dintr-un interval
  (exclude sambata, duminica si sarbatorile legale din tabela sarbatori_legale).
- exista_suprapunere: verifica daca un angajat are deja un concediu APROBAT
  care se suprapune cu intervalul dat (un angajat nu poate fi in 2 concedii
  aprobate in acelasi timp).

Toate datele sunt inclusive (data_start si data_sfarsit fac parte din concediu).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from models import db, Concediu, SarbatoareLegala


def calcul_zile_lucratoare(data_start: date, data_sfarsit: date) -> int:
    """
    Numara zilele lucratoare din intervalul [data_start, data_sfarsit] (inclusiv).

    Exclude weekend-urile (sambata, duminica) si sarbatorile legale.
    Daca intervalul e invalid (sfarsit < start) returneaza 0.
    """
    if not data_start or not data_sfarsit or data_sfarsit < data_start:
        return 0

    # Set cu sarbatorile legale din interval (1 singur query)
    sarbatori = {
        s.data for s in SarbatoareLegala.query.filter(
            SarbatoareLegala.data >= data_start,
            SarbatoareLegala.data <= data_sfarsit,
        ).all()
    }

    zile = 0
    d = data_start
    while d <= data_sfarsit:
        # weekday(): 0=Luni ... 5=Sambata, 6=Duminica
        if d.weekday() < 5 and d not in sarbatori:
            zile += 1
        d += timedelta(days=1)
    return zile


def exista_suprapunere(
    angajat_id: int,
    data_start: date,
    data_sfarsit: date,
    *,
    exclude_id: Optional[int] = None,
    statusuri: tuple = ('aprobat',),
) -> Optional[Concediu]:
    """
    Returneaza primul concediu al angajatului (cu status in `statusuri`) care
    se suprapune cu intervalul [data_start, data_sfarsit], sau None.

    Doua intervale [a1, a2] si [b1, b2] se suprapun daca a1 <= b2 si b1 <= a2.
    `exclude_id` permite ignorarea unei cereri (ex: la editare).
    Implicit verifica doar concediile APROBATE (regula de business: un angajat
    nu poate avea 2 concedii aprobate suprapuse).
    """
    if not data_start or not data_sfarsit:
        return None

    q = Concediu.query.filter(
        Concediu.angajat_id == angajat_id,
        Concediu.status.in_(statusuri),
        Concediu.data_start <= data_sfarsit,
        Concediu.data_sfarsit >= data_start,
    )
    if exclude_id is not None:
        q = q.filter(Concediu.id != exclude_id)
    return q.first()
