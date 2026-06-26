"""Teste pentru helper-ele tenant-safe Gantt."""

from datetime import date

import pytest
from flask import g
from werkzeug.exceptions import HTTPException


SAMPLE = (
    b"cod_articol;denumire;um;cantitate;obiect;tronson;categorie\n"
    b"TA001;Sapatura mecanizata;mc;100;Retea;Strada A;Terasamente\n"
)


@pytest.fixture(autouse=True)
def curata_tenant_access_gantt(app):
    _curata_date(app)
    yield
    _curata_date(app)


def test_query_gantt_plans_strict_scopeaza_direct_si_prin_proiect(app):
    from models import GanttPlan
    from services.security.tenant_access import query_gantt_plans_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        nume = {
            p.nume for p in query_gantt_plans_for_tenant()
            .filter(GanttPlan.nume.like('TA-GANTT-%'))
            .all()
        }

    assert nume == {'TA-GANTT-PLAN-A', 'TA-GANTT-PLAN-A-INHERITED'}


def test_get_gantt_plan_or_404_blocheaza_plan_strain_si_null_operational(app):
    from services.security.tenant_access import get_gantt_plan_or_404

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        with pytest.raises(HTTPException) as foreign_exc:
            get_gantt_plan_or_404(ids['plan_b'])
        with pytest.raises(HTTPException) as ownerless_exc:
            get_gantt_plan_or_404(ids['plan_ownerless'])

    assert foreign_exc.value.code == 404
    assert ownerless_exc.value.code == 404


def test_get_gantt_wbs_node_or_404_blocheaza_nod_strain(app):
    from services.security.tenant_access import get_gantt_wbs_node_or_404

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        with pytest.raises(HTTPException) as exc:
            get_gantt_wbs_node_or_404(ids['node_b'])

    assert exc.value.code == 404


def test_ensure_gantt_inputs_same_tenant_blocheaza_proiect_strain_si_mismatch(app):
    from services.security.tenant_access import (
        TenantAccessDenied,
        ensure_gantt_inputs_same_tenant,
    )

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        with pytest.raises(TenantAccessDenied):
            ensure_gantt_inputs_same_tenant(proiect_id=ids['project_b'])
        with pytest.raises(TenantAccessDenied):
            ensure_gantt_inputs_same_tenant(
                proiect_id=ids['project_b'],
                plan_id=ids['plan_a'],
            )


def test_config_helpers_includ_global_si_tenant_curent_nu_tenant_strain(app):
    from services.security.tenant_access import query_gantt_synonyms_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        sinonime = {
            s.sinonim for s in query_gantt_synonyms_for_tenant()
            .filter_by(camp='denumire')
            .all()
        }

    assert sinonime == {'global-denumire', 'tenant-a-denumire'}


def test_optional_fara_tenant_ramane_permisiv_pentru_migrare(app):
    from models import GanttPlan
    from services.security.tenant_access import query_gantt_plans_for_tenant

    _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'optional'

        nume = {
            p.nume for p in query_gantt_plans_for_tenant()
            .filter(GanttPlan.nume.like('TA-GANTT-PLAN-%'))
            .all()
        }

    assert {'TA-GANTT-PLAN-A', 'TA-GANTT-PLAN-B'} <= nume


def test_off_mode_pastreaza_query_nefiltrat(app):
    from models import GanttPlan
    from services.security.tenant_access import query_gantt_plans_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'off'
        g.tenant_override = ids['tenant_a']

        nume = {
            p.nume for p in query_gantt_plans_for_tenant()
            .filter(GanttPlan.nume.like('TA-GANTT-PLAN-%'))
            .all()
        }

    assert {'TA-GANTT-PLAN-A', 'TA-GANTT-PLAN-B'} <= nume


def _creeaza_date(app):
    from models import (
        GanttPlan, GanttSinonimColoana, GanttWbsNod, Proiect, Tenant, db,
    )

    with app.app_context():
        tenant_a = Tenant(cod='test-ta-gantt-a', nume='Tenant Gantt A')
        tenant_b = Tenant(cod='test-ta-gantt-b', nume='Tenant Gantt B')
        db.session.add_all([tenant_a, tenant_b])
        db.session.commit()

        project_a = _proiect(tenant_a.id, 'TA-GANTT-PRJ-A')
        project_b = _proiect(tenant_b.id, 'TA-GANTT-PRJ-B')
        db.session.add_all([project_a, project_b])
        db.session.commit()

        plan_a = _plan(tenant_a.id, project_a.id, 'TA-GANTT-PLAN-A')
        plan_a_inherited = _plan(None, project_a.id, 'TA-GANTT-PLAN-A-INHERITED')
        plan_b = _plan(tenant_b.id, project_b.id, 'TA-GANTT-PLAN-B')
        plan_ownerless = _plan(None, None, 'TA-GANTT-PLAN-OWNERLESS')
        plan_mismatch = _plan(tenant_a.id, project_b.id, 'TA-GANTT-PLAN-MISMATCH')
        db.session.add_all([plan_a, plan_a_inherited, plan_b, plan_ownerless, plan_mismatch])
        db.session.commit()

        node_a = GanttWbsNod(
            tenant_id=tenant_a.id,
            plan_id=plan_a.id,
            tip='grup',
            nume='TA-GANTT-NOD-A',
            ordine=1,
        )
        node_b = GanttWbsNod(
            tenant_id=tenant_b.id,
            plan_id=plan_b.id,
            tip='grup',
            nume='TA-GANTT-NOD-B',
            ordine=1,
        )
        db.session.add_all([node_a, node_b])

        db.session.add_all([
            GanttSinonimColoana(camp='denumire', sinonim='global-denumire', activ=True),
            GanttSinonimColoana(
                tenant_id=tenant_a.id,
                camp='denumire',
                sinonim='tenant-a-denumire',
                activ=True,
            ),
            GanttSinonimColoana(
                tenant_id=tenant_b.id,
                camp='denumire',
                sinonim='tenant-b-denumire',
                activ=True,
            ),
        ])
        db.session.commit()

        return {
            'tenant_a': tenant_a.id,
            'tenant_b': tenant_b.id,
            'project_b': project_b.id,
            'plan_a': plan_a.id,
            'plan_b': plan_b.id,
            'plan_ownerless': plan_ownerless.id,
            'node_b': node_b.id,
        }


def _proiect(tenant_id, cod):
    from models import Proiect

    return Proiect(
        tenant_id=tenant_id,
        cod_proiect=cod,
        nume=cod,
        data_start=date(2026, 1, 1),
        status='activ',
    )


def _plan(tenant_id, proiect_id, nume):
    from models import GanttPlan

    return GanttPlan(
        tenant_id=tenant_id,
        proiect_id=proiect_id,
        nume=nume,
        nume_fisier=f'{nume}.csv',
        ext='.csv',
        continut=SAMPLE,
        data_start=date(2026, 1, 1),
        nr_activitati=1,
        durata_zile=1,
        cost_total=100,
    )


def _curata_date(app):
    from models import (
        GanttClasificareRegula, GanttPlan, GanttProfilMapare,
        GanttRelatieTemplate, GanttSinonimColoana, GanttWbsNod, Proiect,
        TarifCategorie, Tenant, Utilizator, db,
    )

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        try:
            for cls in (GanttWbsNod, GanttPlan, GanttProfilMapare,
                        GanttSinonimColoana, GanttClasificareRegula,
                        GanttRelatieTemplate):
                for obj in cls.query.all():
                    db.session.delete(obj)
            for row in TarifCategorie.query.filter(
                TarifCategorie.disciplina.like('gantt%')
            ).all():
                db.session.delete(row)
            for proiect in Proiect.query.filter(Proiect.cod_proiect.like('TA-GANTT-%')).all():
                db.session.delete(proiect)
            for tenant in Tenant.query.filter(Tenant.cod.like('test-ta-gantt-%')).all():
                db.session.delete(tenant)
            for user in Utilizator.query.filter(
                Utilizator.email.in_(['admin_test@test.local', 'operator_test@test.local'])
            ).all():
                user.tenant_id = None
            db.session.commit()
        except Exception:
            db.session.rollback()
