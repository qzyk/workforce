"""Teste route-level T1.13 pentru locatii, tokens, mappings si IoT."""

from datetime import date, datetime
from decimal import Decimal

import pytest


@pytest.fixture(autouse=True)
def curata_t113_routes(app):
    _curata_date(app)
    yield
    _curata_date(app)


def test_strict_locatii_filtreaza_si_blocheaza_proiect_strain(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_admin_tenant(app, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    lista = authenticated_client.get(
        f'/locatii/proiect/{ids["proiect_a"]}?format=json'
    )
    proiect_strain = authenticated_client.get(
        f'/locatii/proiect/{ids["proiect_b"]}?format=json'
    )
    edit_strain = authenticated_client.get(f'/locatii/{ids["locatie_b"]}/editeaza')
    delete_strain = authenticated_client.post(f'/locatii/{ids["locatie_b"]}/sterge')
    create_strain = authenticated_client.post(
        f'/locatii/proiect/{ids["proiect_b"]}/nou',
        data={'nume': 'T113 LOC POST STRAIN', 'tip': 'santier', 'status': 'activ'},
    )

    assert lista.status_code == 200
    names = {f['properties']['nume'] for f in lista.get_json()['features']}
    assert names == {'T113 ROUTE LOC A'}
    assert proiect_strain.status_code == 404
    assert edit_strain.status_code == 404
    assert delete_strain.status_code == 404
    assert create_strain.status_code == 404


def test_strict_creare_locatie_asigneaza_tenant_curent(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_admin_tenant(app, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    resp = authenticated_client.post(
        f'/locatii/proiect/{ids["proiect_a"]}/nou',
        data={
            'nume': 'T113 ROUTE LOC NOUA',
            'tip': 'birou',
            'status': 'activ',
            'latitudine': '44.100000',
            'longitudine': '26.100000',
        },
    )

    assert resp.status_code in (302, 303)
    with app.app_context():
        from models import LocatieProiect

        loc = LocatieProiect.query.filter_by(nume='T113 ROUTE LOC NOUA').first()
        assert loc is not None
        assert loc.tenant_id == ids['tenant_a']


def test_off_mode_locatii_ramane_compatibil(authenticated_client, app):
    ids = _creeaza_date(app)
    app.config['MULTI_TENANT_MODE'] = 'off'

    resp = authenticated_client.get(
        f'/locatii/proiect/{ids["proiect_b"]}?format=json'
    )

    assert resp.status_code == 200
    names = {f['properties']['nume'] for f in resp.get_json()['features']}
    assert 'T113 ROUTE LOC B' in names


def test_strict_user_fara_tenant_nu_acceseaza_locatii(operator_client, app):
    ids = _creeaza_date(app)
    app.config['MULTI_TENANT_MODE'] = 'strict'

    resp = operator_client.get(
        f'/locatii/proiect/{ids["proiect_a"]}?format=json'
    )

    assert resp.status_code == 404


def test_strict_tokens_lista_revoke_si_create_sunt_tenant_safe(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_admin_tenant(app, ids['tenant_a'])
    _seteaza_flag(app, 'bim-public-api', True, tenant_id=ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    lista = authenticated_client.get('/bim/tokens')
    revoke_foreign = authenticated_client.post(f'/bim/token/{ids["token_b"]}/revoke')
    create = authenticated_client.post(
        '/bim/token/nou',
        data={'nume': 'T113 Token Nou', 'scopes': ['bim:read']},
    )

    assert lista.status_code == 200
    assert b'T113 Token A' in lista.data
    assert b'T113 Token B' not in lista.data
    assert revoke_foreign.status_code == 404
    assert create.status_code in (302, 303)

    with app.app_context():
        from models import ApiToken

        token_b = ApiToken.query.get(ids['token_b'])
        token_nou = ApiToken.query.filter_by(nume='T113 Token Nou').first()
        assert token_b.activ is True
        assert token_nou is not None
        assert token_nou.tenant_id == ids['tenant_a']


def test_strict_external_mapping_lookup_si_post_sunt_tenant_safe(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_admin_tenant(app, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    own = authenticated_client.get(
        '/bim/api/external-mapping?source_system=manual&extern_id=T113-ROUTE-EXT-A'
    )
    foreign = authenticated_client.get(
        '/bim/api/external-mapping?source_system=manual&extern_id=T113-ROUTE-EXT-B'
    )
    post_foreign = authenticated_client.post(
        '/bim/api/external-mapping',
        json={
            'entity_type': 'element_bim',
            'entity_id': ids['element_b'],
            'source_system': 'manual',
            'extern_id': 'T113-ROUTE-EXT-POST-B',
        },
    )

    assert own.status_code == 200
    assert [row['extern_id'] for row in own.get_json()] == ['T113-ROUTE-EXT-A']
    assert foreign.status_code == 200
    assert foreign.get_json() == []
    assert post_foreign.status_code == 404


def test_strict_iot_routes_scopeaza_senzori_si_alerte(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_admin_tenant(app, ids['tenant_a'])
    _seteaza_flag(app, 'bim-iot-sensors', True, tenant_id=ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    lista = authenticated_client.get('/bim/sensors')
    detail_foreign = authenticated_client.get(f'/bim/sensor/{ids["sensor_b"]}')
    history_foreign = authenticated_client.get(
        f'/bim/api/sensor/{ids["sensor_b"]}/history'
    )
    transition_foreign = authenticated_client.post(
        f'/bim/alert/{ids["alert_b"]}/transition',
        data={'status': 'confirmata'},
    )
    create_own = authenticated_client.post(
        '/bim/sensor/nou',
        data={
            'cod': 'T113-ROUTE-S-NEW',
            'nume': 'T113 Senzor Nou',
            'tip': 'temperatura',
            'element_bim_id': str(ids['element_a']),
        },
    )
    create_foreign = authenticated_client.post(
        '/bim/sensor/nou',
        data={
            'cod': 'T113-ROUTE-S-FOREIGN',
            'nume': 'T113 Senzor Foreign',
            'tip': 'temperatura',
            'element_bim_id': str(ids['element_b']),
        },
    )

    assert lista.status_code == 200
    assert b'T113-ROUTE-S-A' in lista.data
    assert b'T113-ROUTE-S-B' not in lista.data
    assert detail_foreign.status_code == 404
    assert history_foreign.status_code == 404
    assert transition_foreign.status_code == 404
    assert create_own.status_code in (302, 303)
    assert create_foreign.status_code == 404

    with app.app_context():
        from models import SensorAlert, Senzor

        sensor_new = Senzor.query.filter_by(cod='T113-ROUTE-S-NEW').first()
        alert_b = SensorAlert.query.get(ids['alert_b'])
        assert sensor_new is not None
        assert sensor_new.tenant_id == ids['tenant_a']
        assert alert_b.status == 'noua'


def _creeaza_date(app):
    from models import (
        ApiToken, Cladire, ElementBIM, ExternalMapping, FeatureFlag,
        LocatieProiect, ModelBIM, Proiect, Santier, SensorAlert, SensorReading,
        Senzor, Tenant, Utilizator, db,
    )

    with app.app_context():
        for flag in FeatureFlag.query.filter(FeatureFlag.key.in_([
            'bim-public-api',
            'bim-iot-sensors',
        ])).all():
            db.session.delete(flag)

        tenant_a = Tenant(cod='test-t113-route-a', nume='T113 Route A')
        tenant_b = Tenant(cod='test-t113-route-b', nume='T113 Route B')
        db.session.add_all([tenant_a, tenant_b])
        db.session.commit()

        user_a = _user('t113_route_a@test.local', tenant_a.id)
        user_b = _user('t113_route_b@test.local', tenant_b.id)
        db.session.add_all([user_a, user_b])
        db.session.commit()

        proiect_a = _proiect(tenant_a.id, 'T113-ROUTE-PRJ-A')
        proiect_b = _proiect(tenant_b.id, 'T113-ROUTE-PRJ-B')
        db.session.add_all([proiect_a, proiect_b])
        db.session.commit()

        locatie_a = LocatieProiect(
            tenant_id=tenant_a.id,
            proiect_id=proiect_a.id,
            nume='T113 ROUTE LOC A',
            tip='santier',
            status='activ',
            latitudine=Decimal('44.000000'),
            longitudine=Decimal('26.000000'),
        )
        locatie_b = LocatieProiect(
            tenant_id=tenant_b.id,
            proiect_id=proiect_b.id,
            nume='T113 ROUTE LOC B',
            tip='santier',
            status='activ',
            latitudine=Decimal('45.000000'),
            longitudine=Decimal('27.000000'),
        )
        locatie_mix = LocatieProiect(
            tenant_id=tenant_b.id,
            proiect_id=proiect_a.id,
            nume='T113 ROUTE LOC MIX',
            tip='depozit',
            status='activ',
            latitudine=Decimal('44.500000'),
            longitudine=Decimal('26.500000'),
        )
        db.session.add_all([locatie_a, locatie_b, locatie_mix])
        db.session.commit()

        site_a = Santier(
            tenant_id=tenant_a.id,
            proiect_id=proiect_a.id,
            cod='T113-ROUTE-SITE-A',
            nume='T113 Site A',
        )
        site_b = Santier(
            tenant_id=tenant_b.id,
            proiect_id=proiect_b.id,
            cod='T113-ROUTE-SITE-B',
            nume='T113 Site B',
        )
        db.session.add_all([site_a, site_b])
        db.session.commit()

        cladire_a = Cladire(santier_id=site_a.id, cod='T113-ROUTE-BLD-A', nume='A')
        cladire_b = Cladire(santier_id=site_b.id, cod='T113-ROUTE-BLD-B', nume='B')
        db.session.add_all([cladire_a, cladire_b])
        db.session.commit()

        model_a = ModelBIM(
            tenant_id=tenant_a.id,
            santier_id=site_a.id,
            cladire_id=cladire_a.id,
            nume='T113 Route Model A',
            tip='ifc',
            fisier_path='/tmp/t113-route-a.ifc',
        )
        model_b = ModelBIM(
            tenant_id=tenant_b.id,
            santier_id=site_b.id,
            cladire_id=cladire_b.id,
            nume='T113 Route Model B',
            tip='ifc',
            fisier_path='/tmp/t113-route-b.ifc',
        )
        db.session.add_all([model_a, model_b])
        db.session.commit()

        element_a = ElementBIM(
            model_bim_id=model_a.id,
            cladire_id=cladire_a.id,
            cod='T113-ROUTE-EL-A',
            nume='Element A',
            tip_element='wall',
        )
        element_b = ElementBIM(
            model_bim_id=model_b.id,
            cladire_id=cladire_b.id,
            cod='T113-ROUTE-EL-B',
            nume='Element B',
            tip_element='wall',
        )
        db.session.add_all([element_a, element_b])
        db.session.commit()

        sensor_a = Senzor(
            tenant_id=tenant_a.id,
            element_bim_id=element_a.id,
            cod='T113-ROUTE-S-A',
            nume='Senzor A',
            tip='temperatura',
            unitate='C',
            api_key='d' * 64,
        )
        sensor_b = Senzor(
            tenant_id=tenant_b.id,
            element_bim_id=element_b.id,
            cod='T113-ROUTE-S-B',
            nume='Senzor B',
            tip='temperatura',
            unitate='C',
            api_key='e' * 64,
        )
        db.session.add_all([sensor_a, sensor_b])
        db.session.commit()

        reading_a = SensorReading(
            tenant_id=tenant_a.id,
            senzor_id=sensor_a.id,
            ts=datetime.utcnow(),
            valoare=22,
        )
        alert_b = SensorAlert(
            tenant_id=tenant_b.id,
            senzor_id=sensor_b.id,
            tip='peste_max',
            severitate='medie',
            valoare=30,
            mesaj='T113 alert B',
            status='noua',
        )
        db.session.add_all([reading_a, alert_b])
        db.session.commit()

        db.session.add_all([
            ExternalMapping(
                tenant_id=tenant_a.id,
                entity_type='element_bim',
                entity_id=element_a.id,
                source_system='manual',
                extern_id='T113-ROUTE-EXT-A',
            ),
            ExternalMapping(
                tenant_id=tenant_b.id,
                entity_type='element_bim',
                entity_id=element_b.id,
                source_system='manual',
                extern_id='T113-ROUTE-EXT-B',
            ),
        ])
        token_a = _token(tenant_a.id, user_a.id, 'T113 Token A', '4' * 64)
        token_b = _token(tenant_b.id, user_b.id, 'T113 Token B', '5' * 64)
        db.session.add_all([token_a, token_b])
        db.session.commit()

        return {
            'tenant_a': tenant_a.id,
            'tenant_b': tenant_b.id,
            'proiect_a': proiect_a.id,
            'proiect_b': proiect_b.id,
            'locatie_b': locatie_b.id,
            'element_a': element_a.id,
            'element_b': element_b.id,
            'sensor_b': sensor_b.id,
            'alert_b': alert_b.id,
            'token_b': token_b.id,
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


def _user(email, tenant_id):
    from models import Utilizator

    user = Utilizator(
        tenant_id=tenant_id,
        nume='T113',
        prenume=email.split('@')[0],
        email=email,
        rol='admin',
        activ=True,
    )
    user.set_password('test')
    return user


def _token(tenant_id, owner_id, nume, token_plain):
    from models import ApiToken

    token = ApiToken(
        tenant_id=tenant_id,
        owner_id=owner_id,
        nume=nume,
        token=token_plain,
        activ=True,
    )
    token.scopes = ['bim:read']
    return token


def _seteaza_tenant_user(app, user_id, tenant_id):
    from models import Utilizator, db

    with app.app_context():
        user = db.session.get(Utilizator, user_id)
        user.tenant_id = tenant_id
        db.session.commit()


def _seteaza_admin_tenant(app, tenant_id):
    from models import Utilizator, db

    with app.app_context():
        user = Utilizator.query.filter_by(email='admin_test@test.local').first()
        user.tenant_id = tenant_id
        db.session.commit()


def _seteaza_flag(app, key, enabled, tenant_id=None):
    from services.feature_flags import set_flag

    with app.app_context():
        set_flag(key, enabled, tenant_id=tenant_id)


def _curata_date(app):
    from models import (
        ApiToken, Cladire, ElementBIM, ExternalMapping, FeatureFlag,
        LocatieProiect, ModelBIM, Proiect, Santier, SensorAlert, SensorReading,
        Senzor, Tenant, Utilizator, db,
    )

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        for cls in (
            SensorAlert, SensorReading, Senzor, ExternalMapping, ElementBIM,
            ModelBIM, Cladire, Santier, LocatieProiect, ApiToken,
        ):
            for obj in cls.query.all():
                marker = (
                    getattr(obj, 'nume', '')
                    or getattr(obj, 'cod', '')
                    or getattr(obj, 'extern_id', '')
                    or ''
                )
                if str(marker).startswith('T113'):
                    db.session.delete(obj)
        for flag in FeatureFlag.query.filter(FeatureFlag.key.in_([
            'bim-public-api',
            'bim-iot-sensors',
        ])).all():
            db.session.delete(flag)
        for user in Utilizator.query.filter(Utilizator.email.like('t113_route_%')).all():
            db.session.delete(user)
        for user in Utilizator.query.filter(
            Utilizator.email.in_(['admin_test@test.local'])
        ).all():
            user.tenant_id = None
        for proiect in Proiect.query.filter(Proiect.cod_proiect.like('T113-ROUTE-%')).all():
            db.session.delete(proiect)
        for tenant in Tenant.query.filter(Tenant.cod.like('test-t113-route-%')).all():
            db.session.delete(tenant)
        db.session.commit()
