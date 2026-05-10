"""
Integration tests pentru rutele Faza 5 (4D Schedule + 5D Cost).
"""

from datetime import date
import pytest

from models import db, BIMTaskSchedule, BIMCostItem, ElementBIM, Cladire, Santier
from services import feature_flags as ff


@pytest.fixture
def element(app):
    with app.app_context():
        s = Santier(cod='S-INT5', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        el = ElementBIM(cladire_id=c.id, cod='W001', tip_element='wall',
                        status='proiectat', nume='W')
        db.session.add(el); db.session.commit()
        yield {'element_id': el.id, 'santier_id': s.id}


def test_4d_route_redirects_when_flag_off(authenticated_client, app, element):
    with app.app_context():
        ff.set_flag('bim-4d-schedule', False)
    resp = authenticated_client.get(f'/bim/element/{element["element_id"]}/schedule',
                                     follow_redirects=False)
    assert resp.status_code == 302


def test_4d_route_renders_when_flag_on(authenticated_client, app, element):
    with app.app_context():
        ff.set_flag('bim-4d-schedule', True)
    resp = authenticated_client.get(f'/bim/element/{element["element_id"]}/schedule')
    assert resp.status_code == 200


def test_create_schedule_via_route(authenticated_client, app, element):
    with app.app_context():
        ff.set_flag('bim-4d-schedule', True)
        BIMTaskSchedule.query.delete()
        db.session.commit()

    resp = authenticated_client.post(f'/bim/element/{element["element_id"]}/schedule', data={
        'faza': 'structura',
        'data_start_plan': '2026-06-01',
        'data_sfarsit_plan': '2026-06-15',
        'disciplina': 'STR',
    }, follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        sched = BIMTaskSchedule.query.filter_by(element_bim_id=element['element_id']).first()
        assert sched is not None
        assert sched.faza == 'structura'
        assert sched.disciplina == 'STR'


def test_4d_timeline_renders(authenticated_client, app, element):
    with app.app_context():
        ff.set_flag('bim-4d-schedule', True)
    resp = authenticated_client.get(f'/bim/santier/{element["santier_id"]}/4d-timeline')
    assert resp.status_code == 200


def test_api_visible_at_returns_disabled_when_flag_off(authenticated_client, app, element):
    with app.app_context():
        ff.set_flag('bim-4d-schedule', False)
    resp = authenticated_client.get(f'/bim/api/santier/{element["santier_id"]}/visible-at')
    data = resp.get_json()
    assert data['enabled'] is False


def test_api_visible_at_with_data(authenticated_client, app, element):
    """Element cu schedule, query la o data dupa start -> apare in lista."""
    with app.app_context():
        ff.set_flag('bim-4d-schedule', True)
        BIMTaskSchedule.query.delete()
        s = BIMTaskSchedule(
            element_bim_id=element['element_id'],
            faza='structura',
            data_start_plan=date(2026, 1, 1),
            data_sfarsit_plan=date(2026, 3, 1),
            status='planificat', progres_pct=0,
        )
        db.session.add(s); db.session.commit()

    resp = authenticated_client.get(
        f'/bim/api/santier/{element["santier_id"]}/visible-at?data=2026-02-01'
    )
    data = resp.get_json()
    assert data['enabled'] is True
    assert element['element_id'] in data['visible_element_ids']


# ====================================================
# 5D
# ====================================================

def test_5d_route_redirects_when_flag_off(authenticated_client, app, element):
    with app.app_context():
        ff.set_flag('bim-5d-cost', False)
    resp = authenticated_client.get(f'/bim/element/{element["element_id"]}/cost',
                                     follow_redirects=False)
    assert resp.status_code == 302


def test_5d_route_renders_when_flag_on(authenticated_client, app, element):
    with app.app_context():
        ff.set_flag('bim-5d-cost', True)
    resp = authenticated_client.get(f'/bim/element/{element["element_id"]}/cost')
    assert resp.status_code == 200


def test_create_cost_via_route(authenticated_client, app, element):
    with app.app_context():
        ff.set_flag('bim-5d-cost', True)
        BIMCostItem.query.delete()
        db.session.commit()

    resp = authenticated_client.post(f'/bim/element/{element["element_id"]}/cost', data={
        'descriere': 'Beton C25',
        'cantitate': '10.5',
        'pret_unitar': '320.00',
        'categorie': 'material',
        'unitate': 'm3',
        'tip': 'planificat',
    }, follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        item = BIMCostItem.query.filter_by(element_bim_id=element['element_id']).first()
        assert item is not None
        assert float(item.cantitate) == 10.5
        assert float(item.pret_unitar) == 320.0


def test_5d_dashboard_renders(authenticated_client, app, element):
    with app.app_context():
        ff.set_flag('bim-5d-cost', True)
    resp = authenticated_client.get(f'/bim/santier/{element["santier_id"]}/5d-dashboard')
    assert resp.status_code == 200


def test_api_element_cost_returns_disabled_when_flag_off(authenticated_client, app, element):
    with app.app_context():
        ff.set_flag('bim-5d-cost', False)
    resp = authenticated_client.get(f'/bim/api/element/{element["element_id"]}/cost')
    data = resp.get_json()
    assert data['enabled'] is False
