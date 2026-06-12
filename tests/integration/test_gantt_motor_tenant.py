"""
Teste pentru bugfix-ul cache-ului de motor PE TENANT (routes/gantt.py).

Bug istoric: _motor() tinea o singura instanta globala de MotorPlanificare,
deci primul tenant care importa un F3 "fixa" regulile pentru toti ceilalti.
Acum cheia cache-ului include tenant_id: motorul tenantului A nu serveste
regulile tenantului B.
"""
import pytest

from routes import gantt as gantt_routes


@pytest.fixture(autouse=True)
def _curata_motor_si_reguli(app):
    """Cache de motor gol inainte/dupa + sterge regulile si tenantii de test."""
    gantt_routes._invalideaza_motor()
    yield
    gantt_routes._invalideaza_motor()
    from models import db, GanttClasificareRegula, Tenant
    with app.app_context():
        try:
            for row in GanttClasificareRegula.query.filter(
                    GanttClasificareRegula.valoare.like('cuvantmagic-%')).all():
                db.session.delete(row)
            for row in Tenant.query.filter(Tenant.cod.like('test-motor-%')).all():
                db.session.delete(row)
            db.session.commit()
        except Exception:
            db.session.rollback()


def test_motorul_tenantului_a_nu_serveste_regulile_lui_b(app, monkeypatch):
    """Regula de clasificare a tenantului A NU apare in motorul tenantului B."""
    from models import db, GanttClasificareRegula, Tenant
    with app.app_context():
        ta = Tenant(cod='test-motor-a', nume='Tenant test motor A')
        tb = Tenant(cod='test-motor-b', nume='Tenant test motor B')
        db.session.add_all([ta, tb])
        db.session.commit()
        # regula specifica DOAR tenantului A
        db.session.add(GanttClasificareRegula(
            tenant_id=ta.id, categorie='SAPATURA', tip_regula='cuvant',
            valoare='cuvantmagic-tenant-a', prioritate=1))
        db.session.commit()
        id_a, id_b = ta.id, tb.id

        # tenant A -> motorul lui vede regula proprie
        monkeypatch.setattr(gantt_routes, '_tenant_curent', lambda: id_a)
        motor_a = gantt_routes._motor()
        assert motor_a.tenant_id == id_a
        assert 'cuvantmagic-tenant-a' in motor_a.dict_clasificare.get('SAPATURA', [])

        # tenant B -> instanta DIFERITA, fara regula tenantului A (bugfix)
        monkeypatch.setattr(gantt_routes, '_tenant_curent', lambda: id_b)
        motor_b = gantt_routes._motor()
        assert motor_b is not motor_a
        assert motor_b.tenant_id == id_b
        assert 'cuvantmagic-tenant-a' not in motor_b.dict_clasificare.get('SAPATURA', [])

        # cache hit: acelasi tenant -> aceeasi instanta (nu se reincarca config-ul)
        assert gantt_routes._motor() is motor_b
        monkeypatch.setattr(gantt_routes, '_tenant_curent', lambda: id_a)
        assert gantt_routes._motor() is motor_a


def test_invalideaza_motor_goleste_toate_tenanturile(app, monkeypatch):
    """Dupa _invalideaza_motor(), TOATE tenanturile primesc motor reincarcat."""
    monkeypatch.setattr(gantt_routes, '_tenant_curent', lambda: None)
    with app.app_context():
        m1 = gantt_routes._motor()
        assert gantt_routes._motor() is m1
        gantt_routes._invalideaza_motor()
        assert gantt_routes._motor() is not m1
        assert gantt_routes._motor_cache != {}
