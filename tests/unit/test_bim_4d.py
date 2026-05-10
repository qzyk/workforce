"""
Teste unit pentru services.bim_4d (4D Schedule).
"""

from datetime import date, timedelta
import pytest

from models import (db, BIMTaskSchedule, ElementBIM, Cladire, Santier,
                    Utilizator, AuditLog)
from services import bim_4d


@pytest.fixture
def admin(app):
    with app.app_context():
        u = Utilizator.query.filter_by(email='4d_admin@test.local').first()
        if not u:
            u = Utilizator(nume='4D', prenume='X', email='4d_admin@test.local',
                           rol='admin', activ=True)
            u.set_password('x'); db.session.add(u); db.session.commit()
        yield u


@pytest.fixture
def element(app):
    with app.app_context():
        s = Santier(cod='S-4D', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        el = ElementBIM(cladire_id=c.id, cod='W001', tip_element='wall',
                        status='proiectat', nume='W1')
        db.session.add(el); db.session.commit()
        yield {'element_id': el.id, 'santier_id': s.id, 'cladire_id': c.id}


# ====================================================
# create_schedule
# ====================================================

def test_create_schedule_writes_audit(app, element, admin):
    with app.app_context():
        sched = bim_4d.create_schedule(
            element['element_id'], faza='structura',
            data_start_plan=date(2026, 6, 1),
            data_sfarsit_plan=date(2026, 6, 15),
            user=admin,
        )
        assert sched.id is not None
        assert sched.status == 'planificat'
        assert sched.progres_pct == 0
        assert sched.faza == 'structura'
        # Audit
        rows = AuditLog.query.filter_by(entity_type='bim_task_schedule', action='create').count()
        assert rows >= 1


def test_create_invalid_dates_raises(app, element, admin):
    with app.app_context():
        with pytest.raises(ValueError):
            bim_4d.create_schedule(
                element['element_id'], faza='X',
                data_start_plan=date(2026, 6, 15),
                data_sfarsit_plan=date(2026, 6, 1),
                user=admin,
            )


# ====================================================
# update_progress
# ====================================================

def test_update_progress_sets_status_in_curs(app, element, admin):
    with app.app_context():
        s = bim_4d.create_schedule(element['element_id'], 'structura',
                                    date(2026, 6, 1), date(2026, 6, 15), user=admin)
        bim_4d.update_progress(s, 50)
        assert s.progres_pct == 50
        assert s.status == 'in_curs'
        assert s.data_start_real is not None


def test_update_progress_to_100_finalizes(app, element, admin):
    with app.app_context():
        s = bim_4d.create_schedule(element['element_id'], 'structura',
                                    date(2026, 6, 1), date(2026, 6, 15), user=admin)
        bim_4d.update_progress(s, 100)
        assert s.progres_pct == 100
        assert s.status == 'finalizat'
        assert s.data_sfarsit_real is not None


def test_update_progress_clamps_values(app, element, admin):
    with app.app_context():
        s = bim_4d.create_schedule(element['element_id'], 'structura',
                                    date(2026, 6, 1), date(2026, 6, 15), user=admin)
        bim_4d.update_progress(s, 200)  # over 100
        assert s.progres_pct == 100
        bim_4d.update_progress(s, -50)  # under 0
        assert s.progres_pct == 0


# ====================================================
# Queries: visible_at + santier_progress
# ====================================================

def test_visible_at_returns_started_elements(app, element, admin):
    with app.app_context():
        bim_4d.create_schedule(
            element['element_id'], 'structura',
            date(2026, 1, 1), date(2026, 3, 1),
            user=admin,
        )
        # La 2026-02-01 elementul e deja inceput
        visible = bim_4d.get_visible_elements_at_date(element['santier_id'], date(2026, 2, 1))
        assert element['element_id'] in visible
        # La 2025-12-01 nu inceput inca
        visible_before = bim_4d.get_visible_elements_at_date(element['santier_id'], date(2025, 12, 1))
        assert element['element_id'] not in visible_before


def test_compute_santier_progress_empty(app, element):
    with app.app_context():
        progress = bim_4d.compute_santier_progress(element['santier_id'])
        assert progress['total_tasks'] == 0
        assert progress['progres_mediu'] == 0


def test_compute_santier_progress_aggregates(app, element, admin):
    with app.app_context():
        s1 = bim_4d.create_schedule(element['element_id'], 'fundatie',
                                     date(2026, 1, 1), date(2026, 1, 30), user=admin)
        s2 = bim_4d.create_schedule(element['element_id'], 'structura',
                                     date(2026, 2, 1), date(2026, 3, 30), user=admin)
        bim_4d.update_progress(s1, 100)
        bim_4d.update_progress(s2, 50)
        progress = bim_4d.compute_santier_progress(element['santier_id'])
        assert progress['total_tasks'] == 2
        assert progress['finalizate'] == 1
        assert progress['in_curs'] == 1
        # Progres mediu ponderat pe durata - peste 50% (s2 e mai lung)
        assert progress['progres_mediu'] > 50


def test_este_intarziat_property(app, element, admin):
    with app.app_context():
        # Schedule cu sfarsit in trecut, neîterminat
        s = bim_4d.create_schedule(element['element_id'], 'structura',
                                    date(2025, 1, 1), date(2025, 3, 1),
                                    user=admin)
        assert s.este_intarziat is True
        # Daca finalizat, nu mai e intarziat
        bim_4d.update_progress(s, 100)
        assert s.este_intarziat is False
