"""Teste tenant access pentru rutele Gantt."""

from datetime import date
from io import BytesIO

import pytest


SAMPLE = (
    b"cod_articol;denumire;um;cantitate;obiect;tronson;categorie\n"
    b"TA001;Sapatura mecanizata;mc;100;Retea;Strada A;Terasamente\n"
    b"TA002;Pozare conducta PEHD;m;200;Retea;Strada A;Conducte\n"
)


@pytest.fixture(autouse=True)
def curata_gantt_routes(app):
    _curata_date(app)
    yield
    _curata_date(app)


def test_off_mode_plan_open_export_ramane_compatibil(authenticated_client, app):
    ids = _creeaza_date(app)
    app.config['MULTI_TENANT_MODE'] = 'off'

    open_resp = authenticated_client.get(f'/gantt/plan/{ids["plan_b"]}')
    export_resp = authenticated_client.get(f'/gantt/plan/{ids["plan_b"]}/export/csv')

    assert open_resp.status_code == 200
    assert export_resp.status_code == 200
    assert b'Activity Name' in export_resp.data


def test_strict_planuri_listeaza_doar_tenantul_curent(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    resp = authenticated_client.get('/gantt/planuri')

    assert resp.status_code == 200
    assert b'TA-GANTT-PLAN-A' in resp.data
    assert b'TA-GANTT-PLAN-B' not in resp.data
    assert b'TA-GANTT-PLAN-OWNERLESS' not in resp.data


def test_strict_blocheaza_open_export_delete_plan_strain(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    open_resp = authenticated_client.get(f'/gantt/plan/{ids["plan_b"]}')
    export_resp = authenticated_client.get(f'/gantt/plan/{ids["plan_b"]}/export/csv')
    delete_resp = authenticated_client.post(f'/gantt/plan/{ids["plan_b"]}/sterge')

    assert open_resp.status_code == 404
    assert export_resp.status_code == 404
    assert delete_resp.status_code == 404

    with app.app_context():
        from models import GanttPlan, db

        assert db.session.get(GanttPlan, ids['plan_b']) is not None


def test_strict_blocheaza_wbs_plan_si_nod_strain(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    foreign_plan = authenticated_client.get(f'/gantt/plan/{ids["plan_b"]}/wbs')
    foreign_node = authenticated_client.post(
        f'/gantt/plan/{ids["plan_a"]}/wbs/op',
        data={'actiune': 'redenumeste', 'nod_id': ids['node_b'], 'nume': 'NU'},
    )

    assert foreign_plan.status_code == 404
    assert foreign_node.status_code == 404

    with app.app_context():
        from models import GanttWbsNod, db

        assert db.session.get(GanttWbsNod, ids['node_b']).nume == 'TA-GANTT-NOD-B'


def test_strict_save_nu_accepta_proiect_strain_si_planul_primeste_tenant(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    assert _genereaza(authenticated_client).status_code == 200
    foreign = authenticated_client.post(
        '/gantt/salveaza',
        data={'nume': 'TA-GANTT-SAVE-FOREIGN', 'proiect_id': ids['project_b']},
    )
    own = authenticated_client.post(
        '/gantt/salveaza',
        data={'nume': 'TA-GANTT-SAVE-A', 'proiect_id': ids['project_a']},
    )

    assert foreign.status_code == 404
    assert own.status_code == 302

    with app.app_context():
        from models import GanttPlan

        assert GanttPlan.query.filter_by(nume='TA-GANTT-SAVE-FOREIGN').first() is None
        plan = GanttPlan.query.filter_by(nume='TA-GANTT-SAVE-A').first()
        assert plan is not None
        assert plan.tenant_id == ids['tenant_a']
        assert plan.proiect_id == ids['project_a']


def test_strict_user_fara_tenant_esueaza_inchis(operator_client, app):
    ids = _creeaza_date(app)
    app.config['MULTI_TENANT_MODE'] = 'strict'

    resp = operator_client.get(f'/gantt/plan/{ids["plan_a"]}')

    assert resp.status_code == 404


def test_optional_user_fara_tenant_ramane_permisiv(operator_client, app):
    ids = _creeaza_date(app)
    app.config['MULTI_TENANT_MODE'] = 'optional'

    resp = operator_client.get(f'/gantt/plan/{ids["plan_b"]}')

    assert resp.status_code == 200


def test_config_strict_arata_global_si_tenant_curent_fara_tenant_strain(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    resp = authenticated_client.get('/gantt/config')

    assert resp.status_code == 200
    assert b'global-denumire-route' in resp.data
    assert b'tenant-a-denumire-route' in resp.data
    assert b'tenant-b-denumire-route' not in resp.data


def test_config_tenant_write_nu_modifica_global_si_creeaza_rand_tenant(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    toggle_global = authenticated_client.post(
        f'/gantt/config/sinonim/{ids["global_synonym"]}/comuta'
    )
    add_resp = authenticated_client.post(
        '/gantt/config/sinonim',
        data={'camp': 'denumire', 'sinonim': 'tenant-a-nou-route'},
    )

    assert toggle_global.status_code == 302
    assert add_resp.status_code == 302

    with app.app_context():
        from models import GanttSinonimColoana, db

        global_row = db.session.get(GanttSinonimColoana, ids['global_synonym'])
        created = GanttSinonimColoana.query.filter_by(
            sinonim='tenant-a-nou-route'
        ).first()
        assert global_row.activ is True
        assert created is not None
        assert created.tenant_id == ids['tenant_a']


def test_bim_4d_blocheaza_plan_gantt_strain(authenticated_client, app, admin_user):
    ids = _creeaza_date(app, include_bim=True)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    resp = authenticated_client.post(
        f'/bim/model/{ids["model_a"]}/genereaza-4d',
        data={'plan_id': str(ids['plan_b'])},
    )

    assert resp.status_code == 404


def _genereaza(client):
    return client.post(
        '/gantt/genereaza',
        data={'fisier': (BytesIO(SAMPLE), 'ta_gantt.csv')},
        content_type='multipart/form-data',
    )


def _creeaza_date(app, include_bim=False):
    from models import (
        GanttPlan, GanttSinonimColoana, GanttWbsNod, ModelBIM, Proiect,
        Tenant, db,
    )

    with app.app_context():
        tenant_a = Tenant(cod='test-ta-gantt-route-a', nume='Tenant Gantt Route A')
        tenant_b = Tenant(cod='test-ta-gantt-route-b', nume='Tenant Gantt Route B')
        db.session.add_all([tenant_a, tenant_b])
        db.session.commit()

        project_a = _proiect(tenant_a.id, 'TA-GANTT-ROUTE-PRJ-A')
        project_b = _proiect(tenant_b.id, 'TA-GANTT-ROUTE-PRJ-B')
        db.session.add_all([project_a, project_b])
        db.session.commit()

        plan_a = _plan(tenant_a.id, project_a.id, 'TA-GANTT-PLAN-A')
        plan_b = _plan(tenant_b.id, project_b.id, 'TA-GANTT-PLAN-B')
        plan_ownerless = _plan(None, None, 'TA-GANTT-PLAN-OWNERLESS')
        db.session.add_all([plan_a, plan_b, plan_ownerless])
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

        global_synonym = GanttSinonimColoana(
            camp='denumire',
            sinonim='global-denumire-route',
            activ=True,
        )
        synonym_a = GanttSinonimColoana(
            tenant_id=tenant_a.id,
            camp='denumire',
            sinonim='tenant-a-denumire-route',
            activ=True,
        )
        synonym_b = GanttSinonimColoana(
            tenant_id=tenant_b.id,
            camp='denumire',
            sinonim='tenant-b-denumire-route',
            activ=True,
        )
        db.session.add_all([global_synonym, synonym_a, synonym_b])

        model_a = None
        if include_bim:
            model_a = ModelBIM(
                tenant_id=tenant_a.id,
                nume='TA-GANTT-BIM-MODEL-A',
                tip='ifc',
                fisier_path='/tmp/ta-gantt-model-a.ifc',
            )
            db.session.add(model_a)

        db.session.commit()

        ids = {
            'tenant_a': tenant_a.id,
            'tenant_b': tenant_b.id,
            'project_a': project_a.id,
            'project_b': project_b.id,
            'plan_a': plan_a.id,
            'plan_b': plan_b.id,
            'plan_ownerless': plan_ownerless.id,
            'node_b': node_b.id,
            'global_synonym': global_synonym.id,
        }
        if model_a is not None:
            ids['model_a'] = model_a.id
        return ids


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
        nr_activitati=2,
        durata_zile=2,
        cost_total=200,
    )


def _seteaza_tenant_user(app, user_id, tenant_id):
    from models import Utilizator, db

    with app.app_context():
        user = db.session.get(Utilizator, user_id)
        user.tenant_id = tenant_id
        db.session.commit()


def _curata_date(app):
    from models import (
        GanttClasificareRegula, GanttPlan, GanttProfilMapare,
        GanttRelatieTemplate, GanttSinonimColoana, GanttWbsNod, ModelBIM,
        Proiect, TarifCategorie, Tenant, Utilizator, db,
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
            for model in ModelBIM.query.filter(ModelBIM.nume.like('TA-GANTT-%')).all():
                db.session.delete(model)
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
