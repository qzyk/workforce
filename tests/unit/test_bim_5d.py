"""
Teste unit pentru services.bim_5d (5D Cost).
"""

import pytest

from models import (db, BIMCostItem, ElementBIM, Cladire, Santier,
                    Utilizator, AuditLog)
from services import bim_5d


@pytest.fixture
def admin(app):
    with app.app_context():
        u = Utilizator.query.filter_by(email='5d_admin@test.local').first()
        if not u:
            u = Utilizator(nume='5D', prenume='X', email='5d_admin@test.local',
                           rol='admin', activ=True)
            u.set_password('x'); db.session.add(u); db.session.commit()
        yield u


@pytest.fixture
def santier_with_elements(app):
    with app.app_context():
        s = Santier(cod='S-5D', nume='X'); db.session.add(s); db.session.flush()
        c = Cladire(santier_id=s.id, cod='C1', nume='Y'); db.session.add(c); db.session.flush()
        e1 = ElementBIM(cladire_id=c.id, cod='W001', tip_element='wall',
                        status='proiectat', nume='W1')
        e2 = ElementBIM(cladire_id=c.id, cod='D001', tip_element='door',
                        status='proiectat', nume='D1')
        db.session.add_all([e1, e2]); db.session.commit()
        yield {'santier_id': s.id, 'cladire_id': c.id,
               'el_wall_id': e1.id, 'el_door_id': e2.id}


# ====================================================
# create_cost_item
# ====================================================

def test_create_cost_writes_audit(app, santier_with_elements, admin):
    with app.app_context():
        item = bim_5d.create_cost_item(
            santier_with_elements['el_wall_id'],
            descriere='Beton C25', cantitate=10.5, pret_unitar=320.0,
            categorie='material', unitate='m3', user=admin,
        )
        assert item.id is not None
        assert item.total == 10.5 * 320.0
        rows = AuditLog.query.filter_by(entity_type='bim_cost_item', action='create').count()
        assert rows >= 1


def test_negative_quantity_raises(app, santier_with_elements, admin):
    with app.app_context():
        with pytest.raises(ValueError):
            bim_5d.create_cost_item(santier_with_elements['el_wall_id'],
                                    descriere='X', cantitate=-1, pret_unitar=10,
                                    user=admin)


def test_negative_price_raises(app, santier_with_elements, admin):
    with app.app_context():
        with pytest.raises(ValueError):
            bim_5d.create_cost_item(santier_with_elements['el_wall_id'],
                                    descriere='X', cantitate=1, pret_unitar=-10,
                                    user=admin)


# ====================================================
# Aggregations
# ====================================================

def test_cost_total_element_breakdown(app, santier_with_elements, admin):
    with app.app_context():
        eid = santier_with_elements['el_wall_id']
        bim_5d.create_cost_item(eid, 'Beton', 10, 300, categorie='material', user=admin)
        bim_5d.create_cost_item(eid, 'Manopera', 8, 50, categorie='manopera', user=admin)
        result = bim_5d.cost_total_element(eid)
        assert result['total'] == 10*300 + 8*50  # 3400
        assert result['by_categorie']['material'] == 3000
        assert result['by_categorie']['manopera'] == 400
        assert result['count_items'] == 2


def test_cost_breakdown_santier(app, santier_with_elements, admin):
    with app.app_context():
        bim_5d.create_cost_item(santier_with_elements['el_wall_id'],
                                'Beton', 10, 300, categorie='material', user=admin)
        bim_5d.create_cost_item(santier_with_elements['el_door_id'],
                                'Usa', 1, 1500, categorie='material', user=admin)
        breakdown = bim_5d.cost_breakdown_santier(santier_with_elements['santier_id'])
        assert breakdown['total'] == 4500
        assert breakdown['by_tip_element']['wall'] == 3000
        assert breakdown['by_tip_element']['door'] == 1500


def test_cost_planificat_vs_real(app, santier_with_elements, admin):
    with app.app_context():
        sid = santier_with_elements['santier_id']
        eid = santier_with_elements['el_wall_id']
        # Planificat: 1000
        bim_5d.create_cost_item(eid, 'Plan', 10, 100, tip='planificat', user=admin)
        # Real: 1200 (depasit cu 20%)
        bim_5d.create_cost_item(eid, 'Real', 10, 120, tip='real', user=admin)
        delta = bim_5d.cost_planificat_vs_real(sid)
        assert delta['planificat'] == 1000
        assert delta['real'] == 1200
        assert delta['delta'] == 200
        assert delta['delta_pct'] == 20.0


def test_cost_breakdown_empty_santier(app):
    with app.app_context():
        s = Santier(cod='S-EMPTY-5D', nume='X')
        db.session.add(s); db.session.commit()
        breakdown = bim_5d.cost_breakdown_santier(s.id)
        assert breakdown['total'] == 0
        assert breakdown['by_categorie'] == {}


def test_cost_total_filtered_by_tip(app, santier_with_elements, admin):
    with app.app_context():
        eid = santier_with_elements['el_wall_id']
        bim_5d.create_cost_item(eid, 'P', 10, 100, tip='planificat', user=admin)
        bim_5d.create_cost_item(eid, 'R', 10, 120, tip='real', user=admin)
        # Filtrat pe planificat
        result_plan = bim_5d.cost_total_element(eid, tip='planificat')
        assert result_plan['total'] == 1000
        # Filtrat pe real
        result_real = bim_5d.cost_total_element(eid, tip='real')
        assert result_real['total'] == 1200
