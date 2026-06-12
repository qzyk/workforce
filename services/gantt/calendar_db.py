"""
Adaptor DB pentru calendarul de lucru Gantt (separat de calendar.py, care e pur).

Construieste CalendarLucru din modelele GanttCalendar / GanttCalendarExceptie si
sincronizeaza sarbatorile legale (tabelul sarbatori_legale) ca exceptii nelucratoare.

Regula feature flag: `calendar_daca_activ` intoarce un calendar DOAR cand
feature_enabled('gantt-calendar') - cu flag OFF intoarce None, deci apelantii
pastreaza comportamentul istoric (doar Lu-Vi).
"""
from __future__ import annotations

from typing import Optional

from .calendar import CalendarLucru

NUME_CALENDAR_IMPLICIT = 'Calendar RO standard'


def construieste_calendar_lucru(model) -> CalendarLucru:
    """CalendarLucru dintr-un rand GanttCalendar (cu exceptiile lui din DB)."""
    exceptii = {e.data: bool(e.lucratoare) for e in model.exceptii}
    return CalendarLucru(zile_lucratoare=model.zile_lucratoare or '1111100',
                         exceptii=exceptii)


def calendar_implicit(tenant_id: Optional[int] = None):
    """Randul GanttCalendar implicit si activ (intai pe tenant, apoi global) sau None."""
    try:
        from flask import has_app_context
        if not has_app_context():
            return None
        from models import GanttCalendar
        if tenant_id is not None:
            m = (GanttCalendar.query
                 .filter_by(tenant_id=tenant_id, implicit=True, activ=True).first())
            if m is not None:
                return m
        return (GanttCalendar.query
                .filter_by(tenant_id=None, implicit=True, activ=True).first())
    except Exception:
        return None


def calendar_daca_activ(plan=None, tenant_id: Optional[int] = None):
    """CalendarLucru pentru plan/tenant DOAR cand flag-ul 'gantt-calendar' e ON.

    Ordinea: calendarul planului (plan.calendar_id) -> calendarul implicit al
    tenantului -> CalendarLucru() simplu (Lu-Vi, fara sarbatori) daca flag-ul e ON
    dar nu exista nimic configurat in DB. Cu flag OFF -> None (zero regresie).
    """
    try:
        from services.feature_flags import is_enabled
        if not is_enabled('gantt-calendar', tenant_id):
            return None
    except Exception:
        return None
    try:
        model = None
        if plan is not None and getattr(plan, 'calendar_id', None):
            from models import db, GanttCalendar
            model = db.session.get(GanttCalendar, plan.calendar_id)
        if model is None:
            model = calendar_implicit(tenant_id)
        if model is not None:
            return construieste_calendar_lucru(model)
    except Exception:
        pass
    return CalendarLucru()


def sincronizeaza_sarbatori(calendar) -> int:
    """Copiaza sarbatorile legale (sarbatori_legale) ca exceptii nelucratoare pe
    calendarul dat. Idempotent: datele deja existente nu se dubleaza.
    Intoarce numarul de exceptii adaugate."""
    from models import db, GanttCalendarExceptie, SarbatoareLegala
    existente = {e.data for e in GanttCalendarExceptie.query
                 .filter_by(calendar_id=calendar.id).all()}
    adaugate = 0
    for s in SarbatoareLegala.query.order_by(SarbatoareLegala.data).all():
        if s.data in existente:
            continue
        db.session.add(GanttCalendarExceptie(
            calendar_id=calendar.id, data=s.data, lucratoare=False,
            descriere=(s.denumire or '')[:200]))
        existente.add(s.data)
        adaugate += 1
    db.session.commit()
    return adaugate


def creeaza_calendar_implicit(tenant_id: Optional[int] = None):
    """Creeaza calendarul implicit 'Calendar RO standard' daca nu exista si
    sincronizeaza sarbatorile legale. Intoarce (calendar, creat: bool, nr_sarbatori)."""
    from models import db, GanttCalendar
    cal = GanttCalendar.query.filter_by(tenant_id=tenant_id,
                                        nume=NUME_CALENDAR_IMPLICIT).first()
    creat = cal is None
    if creat:
        cal = GanttCalendar(nume=NUME_CALENDAR_IMPLICIT, tenant_id=tenant_id,
                            zile_lucratoare='1111100', ore_pe_zi=8,
                            implicit=True, activ=True)
        db.session.add(cal)
        db.session.commit()
    nr = sincronizeaza_sarbatori(cal)
    return cal, creat, nr
