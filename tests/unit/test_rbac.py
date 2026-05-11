"""
Teste unit pentru services.rbac.
"""

import pytest

from models import db, BIMRoleAssignment, Utilizator
from services import rbac


@pytest.fixture
def admin(app):
    with app.app_context():
        u = Utilizator.query.filter_by(email='rbac_admin@test.local').first()
        if not u:
            u = Utilizator(nume='RBAC', prenume='A', email='rbac_admin@test.local',
                           rol='admin', activ=True)
            u.set_password('x'); db.session.add(u); db.session.commit()
        yield u


@pytest.fixture
def operator(app):
    with app.app_context():
        u = Utilizator.query.filter_by(email='rbac_op@test.local').first()
        if not u:
            u = Utilizator(nume='RBAC', prenume='O', email='rbac_op@test.local',
                           rol='operator', activ=True)
            u.set_password('x'); db.session.add(u); db.session.commit()
        yield u


# ====================================================
# Permission checks
# ====================================================

def test_admin_bypasses_rbac(app, admin):
    """Admin global vede tot, indiferent de RBAC fin."""
    with app.app_context():
        assert rbac.has_permission(admin, 'version:publish') is True
        assert rbac.has_permission(admin, 'iot:write') is True


def test_operator_without_role_has_nothing(app, operator):
    with app.app_context():
        assert rbac.has_permission(operator, 'version:publish') is False
        assert rbac.has_permission(operator, 'cost:write') is False


def test_lead_designer_can_publish_on_own_disciplina(app, operator, admin):
    with app.app_context():
        rbac.assign_role(operator.id, 'lead_designer',
                          scope_type='disciplina', scope_disciplina='ARH',
                          created_by=admin)
        # Pe ARH -> da
        assert rbac.has_permission(operator, 'version:publish', disciplina='ARH') is True
        # Pe STR -> nu
        assert rbac.has_permission(operator, 'version:publish', disciplina='STR') is False
        # Fara disciplina (global) -> nu (rolul e doar pe disciplina)
        assert rbac.has_permission(operator, 'version:publish') is False


def test_reviewer_can_read_only(app, operator, admin):
    with app.app_context():
        rbac.assign_role(operator.id, 'reviewer', scope_type='global',
                          created_by=admin)
        assert rbac.has_permission(operator, 'bim:read') is True
        assert rbac.has_permission(operator, 'cost:read') is True
        assert rbac.has_permission(operator, 'version:publish') is False
        assert rbac.has_permission(operator, 'cost:write') is False


def test_iot_operator_scope(app, operator, admin):
    with app.app_context():
        rbac.assign_role(operator.id, 'iot_operator', scope_type='global',
                          created_by=admin)
        assert rbac.has_permission(operator, 'iot:write') is True
        assert rbac.has_permission(operator, 'bim:write') is False


def test_cost_manager_scope_santier(app, operator, admin):
    """Cost manager pe santier specific."""
    with app.app_context():
        rbac.assign_role(operator.id, 'cost_manager', scope_type='santier',
                          scope_id=5, created_by=admin)
        # Santier 5 -> da
        assert rbac.has_permission(operator, 'cost:write', santier_id=5) is True
        # Santier 6 -> nu
        assert rbac.has_permission(operator, 'cost:write', santier_id=6) is False


def test_revoke_role(app, operator, admin):
    with app.app_context():
        a = rbac.assign_role(operator.id, 'reviewer', created_by=admin)
        assert rbac.has_permission(operator, 'bim:read') is True
        rbac.revoke_role(a)
        assert rbac.has_permission(operator, 'bim:read') is False


def test_invalid_role_raises(app, operator, admin):
    with app.app_context():
        with pytest.raises(ValueError):
            rbac.assign_role(operator.id, 'rol_inventat', created_by=admin)


def test_invalid_scope_type_raises(app, operator, admin):
    with app.app_context():
        with pytest.raises(ValueError):
            rbac.assign_role(operator.id, 'reviewer', scope_type='inventat',
                              created_by=admin)


def test_inactive_assignment_not_in_force(app, operator, admin):
    from datetime import date, timedelta
    with app.app_context():
        # Asignare cu data_sfarsit in trecut
        a = rbac.assign_role(operator.id, 'reviewer',
                              data_sfarsit=date.today() - timedelta(days=1),
                              created_by=admin)
        assert rbac.has_permission(operator, 'bim:read') is False


def test_unauthenticated_returns_false(app):
    with app.app_context():
        assert rbac.has_permission(None, 'bim:read') is False
