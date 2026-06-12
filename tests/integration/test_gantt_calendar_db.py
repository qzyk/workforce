"""
Teste de integrare pentru adaptorul DB al calendarului Gantt
(services/gantt/calendar_db.py) + comanda CLI 'flask init-gantt-calendar'.

Acopera: seed idempotent al sarbatorilor legale, calendarul implicit,
gating-ul pe flag-ul 'gantt-calendar' (OFF -> None, zero regresie).
"""
from datetime import date

import pytest

from services.gantt import calendar_db
from services.gantt.calendar import CalendarLucru


@pytest.fixture(autouse=True)
def _curata_calendare(app):
    """Sterge calendarele Gantt si sarbatorile de test dupa fiecare test."""
    yield
    from models import db, GanttCalendar, GanttCalendarExceptie, SarbatoareLegala
    with app.app_context():
        try:
            for row in GanttCalendarExceptie.query.all():
                db.session.delete(row)
            for row in GanttCalendar.query.all():
                db.session.delete(row)
            for row in SarbatoareLegala.query.filter(
                    SarbatoareLegala.denumire.like('Test sarbatoare%')).all():
                db.session.delete(row)
            db.session.commit()
        except Exception:
            db.session.rollback()


def _adauga_sarbatori_test(db):
    from models import SarbatoareLegala
    zile = [(date(2099, 1, 1), 'Test sarbatoare Anul Nou'),
            (date(2099, 12, 1), 'Test sarbatoare Ziua Nationala')]
    for d, nume in zile:
        if not SarbatoareLegala.query.filter_by(data=d).first():
            db.session.add(SarbatoareLegala(data=d, denumire=nume, an=d.year))
    db.session.commit()
    return [d for d, _ in zile]


def test_sincronizeaza_sarbatori_idempotent(app):
    """A doua rulare nu dubleaza exceptiile (0 adaugate, acelasi numar de randuri)."""
    from models import db, GanttCalendar, GanttCalendarExceptie
    with app.app_context():
        zile = _adauga_sarbatori_test(db)
        cal = GanttCalendar(nume='Calendar test sync', zile_lucratoare='1111100')
        db.session.add(cal)
        db.session.commit()

        nr1 = calendar_db.sincronizeaza_sarbatori(cal)
        assert nr1 >= len(zile)
        total1 = GanttCalendarExceptie.query.filter_by(calendar_id=cal.id).count()

        nr2 = calendar_db.sincronizeaza_sarbatori(cal)
        assert nr2 == 0                       # idempotent: nimic de adaugat
        total2 = GanttCalendarExceptie.query.filter_by(calendar_id=cal.id).count()
        assert total2 == total1               # fara duplicate

        # exceptiile sincronizate sunt nelucratoare
        e = (GanttCalendarExceptie.query
             .filter_by(calendar_id=cal.id, data=zile[0]).first())
        assert e is not None and e.lucratoare is False


def test_creeaza_calendar_implicit_idempotent(app):
    """'Calendar RO standard' se creeaza o singura data, apoi doar se sincronizeaza."""
    from models import db, GanttCalendar
    with app.app_context():
        _adauga_sarbatori_test(db)
        cal1, creat1, _ = calendar_db.creeaza_calendar_implicit()
        assert creat1 is True and cal1.nume == calendar_db.NUME_CALENDAR_IMPLICIT
        assert cal1.implicit is True and cal1.activ is True

        cal2, creat2, nr2 = calendar_db.creeaza_calendar_implicit()
        assert creat2 is False and cal2.id == cal1.id and nr2 == 0
        assert GanttCalendar.query.filter_by(
            nume=calendar_db.NUME_CALENDAR_IMPLICIT, tenant_id=None).count() == 1


def test_calendar_daca_activ_flag_off_intoarce_none(app):
    """Flag OFF (default) -> None, deci apelantii raman pe comportamentul istoric."""
    with app.app_context():
        assert calendar_db.calendar_daca_activ() is None


def test_calendar_daca_activ_flag_on_intoarce_calendar_cu_sarbatori(app):
    """Flag ON -> CalendarLucru construit din calendarul implicit, cu sarbatorile
    legale ca zile nelucratoare."""
    from models import db
    from services.feature_flags import set_flag
    with app.app_context():
        zile = _adauga_sarbatori_test(db)
        calendar_db.creeaza_calendar_implicit()
        set_flag('gantt-calendar', True)

        cal = calendar_db.calendar_daca_activ()
        assert isinstance(cal, CalendarLucru)
        for d in zile:
            assert cal.este_lucratoare(d) is False
        # zi normala de lucru ramane lucratoare (2099-01-02 e vineri)
        assert cal.este_lucratoare(date(2099, 1, 2)) is True


def test_cli_init_gantt_calendar(app):
    """Comanda 'flask init-gantt-calendar' creeaza calendarul si e idempotenta."""
    from models import db, GanttCalendar
    with app.app_context():
        _adauga_sarbatori_test(db)
    runner = app.test_cli_runner()

    r1 = runner.invoke(args=['init-gantt-calendar'])
    assert r1.exit_code == 0 and 'creat' in r1.output

    r2 = runner.invoke(args=['init-gantt-calendar'])
    assert r2.exit_code == 0 and 'existent' in r2.output

    with app.app_context():
        assert GanttCalendar.query.filter_by(
            nume=calendar_db.NUME_CALENDAR_IMPLICIT, tenant_id=None).count() == 1
