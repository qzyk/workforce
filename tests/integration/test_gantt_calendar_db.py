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


# DDL-ul gantt_plan FARA calendar_id - schema dinainte de calendar
# (creata de migratia 0013_gantt_plan, inainte de 0021_gantt_calendar).
_DDL_GANTT_PLAN_VECHI = """
CREATE TABLE gantt_plan (
    id INTEGER NOT NULL,
    tenant_id INTEGER,
    proiect_id INTEGER,
    obiect_id INTEGER,
    nume VARCHAR(160) NOT NULL,
    nume_fisier VARCHAR(255),
    ext VARCHAR(10),
    continut BLOB NOT NULL,
    mapare_json TEXT,
    data_start DATE,
    nr_activitati INTEGER NOT NULL,
    durata_zile INTEGER NOT NULL,
    cost_total NUMERIC(16, 2) NOT NULL,
    creat_de_id INTEGER,
    data_creare DATETIME NOT NULL,
    data_actualizare DATETIME,
    PRIMARY KEY (id),
    FOREIGN KEY(creat_de_id) REFERENCES utilizatori (id),
    FOREIGN KEY(proiect_id) REFERENCES proiecte (id),
    FOREIGN KEY(obiect_id) REFERENCES obiect (id),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)
"""


def test_cli_adauga_coloana_calendar_id_pe_schema_veche(app):
    """Simuleaza prod la 0017 (gantt_plan FARA calendar_id, fara tabele calendar)
    si verifica ca CLI-ul adauga coloana cu ALTER idempotent.

    Capcana reprodusa la review: db.create_all() creeaza doar tabelele lipsa,
    NU adauga coloane pe tabele existente - fara ALTER, GanttPlan.query crapa
    cu 'no such column: gantt_plan.calendar_id' imediat dupa deploy, chiar si
    cu flag-ul 'gantt-calendar' OFF.
    """
    from datetime import datetime
    from sqlalchemy import inspect, text
    from sqlalchemy.exc import OperationalError
    from models import db, GanttPlan

    with app.app_context():
        # 1. Aduce schema la starea prod 0017: gantt_plan vechi, fara calendar
        with db.engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS gantt_plan'))
            conn.execute(text('DROP TABLE IF EXISTS gantt_calendar_exceptie'))
            conn.execute(text('DROP TABLE IF EXISTS gantt_calendar'))
            conn.execute(text(_DDL_GANTT_PLAN_VECHI))
            conn.execute(text('CREATE INDEX ix_gantt_plan_tenant_proiect '
                              'ON gantt_plan (tenant_id, proiect_id)'))
            # un rand existent, ca pe prod (plan salvat inainte de deploy)
            conn.execute(text(
                "INSERT INTO gantt_plan (nume, continut, nr_activitati, "
                "durata_zile, cost_total, data_creare) "
                "VALUES ('Plan vechi prod', x'00', 0, 0, 0, :acum)"),
                {'acum': datetime.utcnow()})
        db.session.remove()

        # 2. Reproducere bug: modelul mapeaza calendar_id -> query-ul crapa
        with pytest.raises(OperationalError):
            GanttPlan.query.first()
        db.session.rollback()

    # 3. Ruleaza CLI-ul (pasul de deploy) - trebuie sa repare schema
    runner = app.test_cli_runner()
    r1 = runner.invoke(args=['init-gantt-calendar'])
    assert r1.exit_code == 0
    assert 'calendar_id adaugata' in r1.output

    with app.app_context():
        # 4. Coloana exista, query-ul pe GanttPlan nu mai crapa, datele au ramas
        cols = {c['name'] for c in inspect(db.engine).get_columns('gantt_plan')}
        assert 'calendar_id' in cols
        plan = GanttPlan.query.first()
        assert plan is not None and plan.nume == 'Plan vechi prod'
        assert plan.calendar_id is None

    # 5. Idempotent: a doua rulare nu mai face ALTER si nu da eroare
    r2 = runner.invoke(args=['init-gantt-calendar'])
    assert r2.exit_code == 0
    assert 'calendar_id exista deja' in r2.output

    # 6. Curatenie ROBUSTA: testul a recreat manual gantt_plan dintr-un DDL
    # snapshot, care poate ramane in urma schemei reale (ex. coloane noi
    # adaugate de alte module). Pentru a NU polua sesiunea (DB-ul e
    # session-scoped si partajat cu restul testelor), dam DROP la tabelele
    # atinse si le recreem din modelele CURENTE via db.create_all().
    with app.app_context():
        with db.engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS gantt_plan'))
            conn.execute(text('DROP TABLE IF EXISTS gantt_calendar_exceptie'))
            conn.execute(text('DROP TABLE IF EXISTS gantt_calendar'))
        db.session.remove()
        db.create_all()  # reface schema completa din models (toate coloanele)
