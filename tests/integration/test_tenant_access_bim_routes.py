"""Teste tenant access pentru rutele BIM."""

from datetime import date
from io import BytesIO
from zipfile import ZipFile

import pytest


@pytest.fixture(autouse=True)
def curata_bim_routes(app):
    _curata_date(app)
    yield
    _curata_date(app)


def test_off_mode_model_file_ramane_compatibil(authenticated_client, app, tmp_path):
    ids = _creeaza_date(app, tmp_path)
    app.config['MULTI_TENANT_MODE'] = 'off'

    resp = authenticated_client.get(f'/bim/viewer/{ids["model_b"]}/file')

    assert resp.status_code == 200
    assert resp.data == b'IFC-B'


def test_strict_dashboard_tree_si_liste_scopeaza_tenant(
    authenticated_client, app, admin_user, tmp_path
):
    ids = _creeaza_date(app, tmp_path)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    dashboard = authenticated_client.get('/bim/')
    tree = authenticated_client.get('/bim/api/tree')
    modele = authenticated_client.get('/bim/modele')
    issues = authenticated_client.get('/bim/issues')

    assert dashboard.status_code == 200
    assert b'TA-BIM-SITE-A' in dashboard.data
    assert b'TA-BIM-SITE-B' not in dashboard.data
    assert [s['cod'] for s in tree.get_json()] == ['TA-BIM-SITE-A']
    assert b'TA-BIM-MODEL-A' in modele.data
    assert b'TA-BIM-MODEL-B' not in modele.data
    assert b'TA-BIM-ISSUE-A' in issues.data
    assert b'TA-BIM-ISSUE-B' not in issues.data


def test_strict_blocheaza_santier_model_element_issue_straine(
    authenticated_client, app, admin_user, tmp_path
):
    ids = _creeaza_date(app, tmp_path)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    assert authenticated_client.get(f'/bim/santier/{ids["site_b"]}').status_code == 404
    assert authenticated_client.get(f'/bim/viewer/{ids["model_b"]}').status_code == 404
    assert authenticated_client.get(f'/bim/element/{ids["element_b"]}').status_code == 404
    assert authenticated_client.get(f'/bim/api/element/{ids["element_b"]}').status_code == 404
    assert authenticated_client.get(f'/bim/api/issue/{ids["issue_b"]}/comments').status_code == 404


def test_strict_blocheaza_download_model_si_versiune_straina(
    authenticated_client, app, admin_user, tmp_path
):
    ids = _creeaza_date(app, tmp_path)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    model_file = authenticated_client.get(f'/bim/viewer/{ids["model_b"]}/file')
    version_file = authenticated_client.get(
        f'/bim/api/model-version/{ids["version_b"]}/file'
    )

    assert model_file.status_code == 404
    assert version_file.status_code == 404


def test_strict_blocheaza_status_si_comentariu_pe_issue_strain(
    authenticated_client, app, admin_user, tmp_path
):
    ids = _creeaza_date(app, tmp_path)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    _seteaza_flag(app, 'bim-realtime-collab', True, tenant_id=ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    status = authenticated_client.post(
        f'/bim/issue/{ids["issue_b"]}/status',
        data={'status': 'inchis'},
    )
    comment = authenticated_client.post(
        f'/bim/issue/{ids["issue_b"]}/comments',
        data={'text': 'comentariu strain'},
    )

    assert status.status_code == 404
    assert comment.status_code == 404

    with app.app_context():
        from models import BIMComment, IssueBIM

        issue_b = IssueBIM.query.get(ids['issue_b'])
        assert issue_b.status == 'deschis'
        assert BIMComment.query.filter_by(issue_id=ids['issue_b']).count() == 0


def test_strict_export_bcf_all_include_doar_issue_tenant_si_mixed_ids_esueaza(
    authenticated_client, app, admin_user, tmp_path
):
    ids = _creeaza_date(app, tmp_path)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    _seteaza_flag(app, 'bim-bcf-full', True, tenant_id=ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    export_all = authenticated_client.get('/bim/issues/export-bcf')
    mixed = authenticated_client.get(
        f'/bim/issues/export-bcf?ids={ids["issue_a"]},{ids["issue_b"]}'
    )

    assert export_all.status_code == 200
    assert mixed.status_code == 404

    with ZipFile(BytesIO(export_all.data)) as zf:
        text = '\n'.join(
            zf.read(name).decode('utf-8')
            for name in zf.namelist()
            if name.endswith('markup.bcf')
        )

    assert 'TA-BIM-ISSUE-A' in text
    assert 'TA-BIM-ISSUE-B' not in text


def test_strict_import_ifc_nu_accepta_santier_strain(
    authenticated_client, app, admin_user, tmp_path
):
    ids = _creeaza_date(app, tmp_path)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    resp = authenticated_client.post(
        '/bim/import/ifc',
        data={
            'santier_id': str(ids['site_b']),
            'ifc_file': (BytesIO(b'ISO-10303-21;'), 'ta-bim.ifc'),
        },
        content_type='multipart/form-data',
    )

    assert resp.status_code == 404


def test_strict_teren_nu_creeaza_issue_pe_santier_strain(
    authenticated_client, app, admin_user, tmp_path
):
    ids = _creeaza_date(app, tmp_path)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    resp = authenticated_client.post(
        '/teren/problema',
        data={
            'titlu': 'TA-BIM-FIELD-FOREIGN',
            'severitate': 'mare',
            'santier_id': str(ids['site_b']),
        },
    )

    assert resp.status_code == 404

    with app.app_context():
        from models import IssueBIM

        assert IssueBIM.query.filter_by(titlu='TA-BIM-FIELD-FOREIGN').first() is None


def test_strict_user_fara_tenant_esueaza_inchis(operator_client, app, tmp_path):
    ids = _creeaza_date(app, tmp_path)
    app.config['MULTI_TENANT_MODE'] = 'strict'

    resp = operator_client.get(f'/bim/santier/{ids["site_a"]}')

    assert resp.status_code == 404


def test_optional_mode_user_fara_tenant_ramane_permisiv(
    authenticated_client, app, admin_user, tmp_path
):
    _creeaza_date(app, tmp_path)
    _seteaza_tenant_user(app, admin_user.id, None)
    app.config['MULTI_TENANT_MODE'] = 'optional'

    tree = authenticated_client.get('/bim/api/tree')

    assert tree.status_code == 200
    assert {s['cod'] for s in tree.get_json()} == {'TA-BIM-SITE-A', 'TA-BIM-SITE-B'}


def _creeaza_date(app, tmp_path):
    from models import (
        BIMModelVersion, Cladire, ElementBIM, IssueBIM, ModelBIM, Proiect,
        Santier, Tenant, db,
    )

    with app.app_context():
        tenant_a = Tenant(cod='test-ta-bim-route-a', nume='Tenant BIM Route A')
        tenant_b = Tenant(cod='test-ta-bim-route-b', nume='Tenant BIM Route B')
        db.session.add_all([tenant_a, tenant_b])
        db.session.commit()

        proiect_a = _proiect(tenant_a.id, 'TA-BIM-ROUTE-PRJ-A')
        proiect_b = _proiect(tenant_b.id, 'TA-BIM-ROUTE-PRJ-B')
        db.session.add_all([proiect_a, proiect_b])
        db.session.commit()

        site_a = Santier(
            tenant_id=tenant_a.id,
            proiect_id=proiect_a.id,
            cod='TA-BIM-SITE-A',
            nume='TA BIM Site A',
        )
        site_b = Santier(
            tenant_id=tenant_b.id,
            proiect_id=proiect_b.id,
            cod='TA-BIM-SITE-B',
            nume='TA BIM Site B',
        )
        db.session.add_all([site_a, site_b])
        db.session.commit()

        cladire_a = Cladire(santier_id=site_a.id, cod='TA-BIM-BLD-A', nume='A')
        cladire_b = Cladire(santier_id=site_b.id, cod='TA-BIM-BLD-B', nume='B')
        db.session.add_all([cladire_a, cladire_b])
        db.session.commit()

        file_a = tmp_path / 'ta_bim_model_a.ifc'
        file_b = tmp_path / 'ta_bim_model_b.ifc'
        version_a_file = tmp_path / 'ta_bim_version_a.ifc'
        version_b_file = tmp_path / 'ta_bim_version_b.ifc'
        file_a.write_bytes(b'IFC-A')
        file_b.write_bytes(b'IFC-B')
        version_a_file.write_bytes(b'VER-A')
        version_b_file.write_bytes(b'VER-B')

        model_a = ModelBIM(
            tenant_id=tenant_a.id,
            santier_id=site_a.id,
            cladire_id=cladire_a.id,
            nume='TA-BIM-MODEL-A',
            tip='ifc',
            fisier_path=str(file_a),
        )
        model_b = ModelBIM(
            tenant_id=tenant_b.id,
            santier_id=site_b.id,
            cladire_id=cladire_b.id,
            nume='TA-BIM-MODEL-B',
            tip='ifc',
            fisier_path=str(file_b),
        )
        db.session.add_all([model_a, model_b])
        db.session.commit()

        version_a = BIMModelVersion(
            tenant_id=tenant_a.id,
            model_id=model_a.id,
            versiune='A',
            status='published',
            fisier_path=str(version_a_file),
        )
        version_b = BIMModelVersion(
            tenant_id=tenant_b.id,
            model_id=model_b.id,
            versiune='B',
            status='published',
            fisier_path=str(version_b_file),
        )
        db.session.add_all([version_a, version_b])
        db.session.commit()

        element_a = ElementBIM(
            model_bim_id=model_a.id,
            cladire_id=cladire_a.id,
            cod='TA-BIM-EL-A',
            nume='Element A',
            tip_element='wall',
        )
        element_b = ElementBIM(
            model_bim_id=model_b.id,
            cladire_id=cladire_b.id,
            cod='TA-BIM-EL-B',
            nume='Element B',
            tip_element='wall',
        )
        db.session.add_all([element_a, element_b])
        db.session.commit()

        issue_a = IssueBIM(
            tenant_id=tenant_a.id,
            element_bim_id=element_a.id,
            cladire_id=cladire_a.id,
            titlu='TA-BIM-ISSUE-A',
            status='deschis',
            bcf_topic_guid='ta-bim-issue-a-guid',
        )
        issue_b = IssueBIM(
            tenant_id=tenant_b.id,
            element_bim_id=element_b.id,
            cladire_id=cladire_b.id,
            titlu='TA-BIM-ISSUE-B',
            status='deschis',
            bcf_topic_guid='ta-bim-issue-b-guid',
        )
        db.session.add_all([issue_a, issue_b])
        db.session.commit()

        return {
            'tenant_a': tenant_a.id,
            'tenant_b': tenant_b.id,
            'site_a': site_a.id,
            'site_b': site_b.id,
            'model_b': model_b.id,
            'version_b': version_b.id,
            'element_b': element_b.id,
            'issue_a': issue_a.id,
            'issue_b': issue_b.id,
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


def _seteaza_tenant_user(app, user_id, tenant_id):
    from models import Utilizator, db

    with app.app_context():
        user = db.session.get(Utilizator, user_id)
        user.tenant_id = tenant_id
        db.session.commit()


def _seteaza_flag(app, key, enabled, tenant_id=None):
    from services.feature_flags import set_flag

    with app.app_context():
        set_flag(key, enabled, tenant_id=tenant_id)


def _curata_date(app):
    from models import (
        BIMComment, BIMModelVersion, Cladire, ElementBIM, FeatureFlag, IssueBIM,
        ModelBIM, Proiect, Santier, Tenant, Utilizator, db,
    )

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        for cls in (BIMComment, BIMModelVersion, IssueBIM, ElementBIM, ModelBIM, Cladire, Santier):
            for obj in cls.query.all():
                db.session.delete(obj)
        for flag in FeatureFlag.query.filter(FeatureFlag.key.in_([
            'bim-realtime-collab',
            'bim-bcf-full',
        ])).all():
            db.session.delete(flag)
        for user in Utilizator.query.filter(
            Utilizator.email.in_([
                'admin_test@test.local',
                'operator_test@test.local',
            ])
        ).all():
            user.tenant_id = None
        for proiect in Proiect.query.filter(Proiect.cod_proiect.like('TA-BIM-%')).all():
            db.session.delete(proiect)
        for tenant in Tenant.query.filter(Tenant.cod.like('test-ta-bim-route-%')).all():
            db.session.delete(tenant)
        db.session.commit()
