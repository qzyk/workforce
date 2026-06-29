"""Teste pentru helper-ele T1.13: locatii, audit, tokens, IoT."""

from datetime import date, datetime

import pytest
from flask import g
from werkzeug.exceptions import HTTPException


@pytest.fixture(autouse=True)
def curata_t113_unit(app):
    _curata_date(app)
    yield
    _curata_date(app)


def test_query_project_locations_strict_exclude_locatii_straine_si_mixte(app):
    from models import LocatieProiect
    from services.security.tenant_access import query_project_locations_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        locatii = query_project_locations_for_tenant(
            project_id=ids['proiect_a']
        ).order_by(LocatieProiect.nume).all()

    assert [l.nume for l in locatii] == ['T113 LOC A', 'T113 LOC A legacy']


def test_get_project_location_or_404_blocheaza_locatie_straina(app):
    from services.security.tenant_access import get_project_location_or_404

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        with pytest.raises(HTTPException) as exc:
            get_project_location_or_404(ids['locatie_b'])

    assert exc.value.code == 404


def test_api_tokens_strict_scopeaza_owner_si_respinge_mismatch(app):
    from services import api_tokens as tokens_svc
    from services.security.tenant_access import query_api_tokens_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        tokens = query_api_tokens_for_tenant().all()
        assert {t.nume for t in tokens} == {'T113 Token A'}
        assert tokens_svc.authenticate_token(ids['token_a_plain']).id == ids['token_a']
        assert tokens_svc.authenticate_token(ids['token_mismatch_plain']) is None
        with pytest.raises(ValueError):
            tokens_svc.create_token(
                'T113 invalid',
                ids['user_a'],
                ['bim:read'],
                tenant_id=ids['tenant_b'],
            )


def test_audit_logs_strict_scopeaza_tenant_si_user_fallback(app):
    from models import AuditLog
    from services.security.tenant_access import query_audit_logs_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        rows = query_audit_logs_for_tenant().order_by(AuditLog.entity_type).all()

    assert {row.entity_type for row in rows} == {'t113_audit_a', 't113_audit_legacy_a'}


def test_iot_si_external_mapping_strict_scopeaza_tenant_si_owner_bim(app):
    from models import ExternalMapping, Senzor, SensorAlert, SensorReading
    from services.security.tenant_access import (
        query_external_mappings_for_tenant,
        query_sensor_alerts_for_tenant,
        query_sensor_readings_for_tenant,
        query_sensors_for_tenant,
    )

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        mappings = query_external_mappings_for_tenant().order_by(
            ExternalMapping.extern_id
        ).all()
        senzori = query_sensors_for_tenant().order_by(Senzor.cod).all()
        readings = query_sensor_readings_for_tenant().order_by(SensorReading.id).all()
        alerts = query_sensor_alerts_for_tenant().order_by(SensorAlert.id).all()

    assert {m.extern_id for m in mappings} == {'T113-EXT-A', 'T113-EXT-A-LEGACY'}
    assert {s.cod for s in senzori} == {'T113-S-A', 'T113-S-A-LEGACY'}
    assert [r.senzor_id for r in readings] == [ids['sensor_a']]
    assert [a.senzor_id for a in alerts] == [ids['sensor_a']]


def test_get_helpers_t113_blocheaza_recorduri_straine(app):
    from services.security.tenant_access import (
        get_api_token_or_404,
        get_external_mapping_or_404,
        get_sensor_alert_or_404,
        get_sensor_or_404,
    )

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        for helper, object_id in (
            (get_api_token_or_404, ids['token_b']),
            (get_external_mapping_or_404, ids['mapping_b']),
            (get_sensor_or_404, ids['sensor_b']),
            (get_sensor_alert_or_404, ids['alert_b']),
        ):
            with pytest.raises(HTTPException) as exc:
                helper(object_id)
            assert exc.value.code == 404


def test_off_mode_ramane_permisiv_pentru_helper_t113(app):
    from services.security.tenant_access import (
        query_api_tokens_for_tenant,
        query_project_locations_for_tenant,
        query_sensors_for_tenant,
    )

    _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'off'

        assert query_project_locations_for_tenant().count() >= 4
        assert query_api_tokens_for_tenant().count() >= 3
        assert query_sensors_for_tenant().count() >= 3


def _creeaza_date(app):
    from models import (
        ApiToken, AuditLog, Cladire, ElementBIM, ExternalMapping, LocatieProiect,
        ModelBIM, Proiect, Santier, SensorAlert, SensorReading, Senzor,
        Tenant, Utilizator, db,
    )

    with app.app_context():
        tenant_a = Tenant(cod='test-t113-unit-a', nume='T113 Unit A')
        tenant_b = Tenant(cod='test-t113-unit-b', nume='T113 Unit B')
        db.session.add_all([tenant_a, tenant_b])
        db.session.commit()

        user_a = _user('t113_unit_a@test.local', tenant_a.id)
        user_b = _user('t113_unit_b@test.local', tenant_b.id)
        db.session.add_all([user_a, user_b])
        db.session.commit()

        proiect_a = _proiect(tenant_a.id, 'T113-UNIT-PRJ-A')
        proiect_b = _proiect(tenant_b.id, 'T113-UNIT-PRJ-B')
        db.session.add_all([proiect_a, proiect_b])
        db.session.commit()

        locatie_a = LocatieProiect(
            tenant_id=tenant_a.id,
            proiect_id=proiect_a.id,
            nume='T113 LOC A',
            tip='santier',
            status='activ',
        )
        locatie_a_legacy = LocatieProiect(
            tenant_id=None,
            proiect_id=proiect_a.id,
            nume='T113 LOC A legacy',
            tip='birou',
            status='activ',
        )
        locatie_b = LocatieProiect(
            tenant_id=tenant_b.id,
            proiect_id=proiect_b.id,
            nume='T113 LOC B',
            tip='santier',
            status='activ',
        )
        locatie_mix = LocatieProiect(
            tenant_id=tenant_b.id,
            proiect_id=proiect_a.id,
            nume='T113 LOC MIX',
            tip='depozit',
            status='activ',
        )
        db.session.add_all([locatie_a, locatie_a_legacy, locatie_b, locatie_mix])
        db.session.commit()

        site_a = Santier(
            tenant_id=tenant_a.id,
            proiect_id=proiect_a.id,
            cod='T113-UNIT-SITE-A',
            nume='T113 Site A',
        )
        site_b = Santier(
            tenant_id=tenant_b.id,
            proiect_id=proiect_b.id,
            cod='T113-UNIT-SITE-B',
            nume='T113 Site B',
        )
        db.session.add_all([site_a, site_b])
        db.session.commit()

        cladire_a = Cladire(santier_id=site_a.id, cod='T113-UNIT-BLD-A', nume='A')
        cladire_b = Cladire(santier_id=site_b.id, cod='T113-UNIT-BLD-B', nume='B')
        db.session.add_all([cladire_a, cladire_b])
        db.session.commit()

        model_a = ModelBIM(
            tenant_id=tenant_a.id,
            santier_id=site_a.id,
            cladire_id=cladire_a.id,
            nume='T113 Unit Model A',
            tip='ifc',
            fisier_path='/tmp/t113-unit-a.ifc',
        )
        model_b = ModelBIM(
            tenant_id=tenant_b.id,
            santier_id=site_b.id,
            cladire_id=cladire_b.id,
            nume='T113 Unit Model B',
            tip='ifc',
            fisier_path='/tmp/t113-unit-b.ifc',
        )
        db.session.add_all([model_a, model_b])
        db.session.commit()

        element_a = ElementBIM(
            model_bim_id=model_a.id,
            cladire_id=cladire_a.id,
            cod='T113-UNIT-EL-A',
            nume='Element A',
            tip_element='wall',
        )
        element_b = ElementBIM(
            model_bim_id=model_b.id,
            cladire_id=cladire_b.id,
            cod='T113-UNIT-EL-B',
            nume='Element B',
            tip_element='wall',
        )
        db.session.add_all([element_a, element_b])
        db.session.commit()

        sensor_a = Senzor(
            tenant_id=tenant_a.id,
            element_bim_id=element_a.id,
            cod='T113-S-A',
            nume='Senzor A',
            tip='temperatura',
            unitate='C',
            api_key='a' * 64,
        )
        sensor_a_legacy = Senzor(
            tenant_id=None,
            element_bim_id=element_a.id,
            cod='T113-S-A-LEGACY',
            nume='Senzor A legacy',
            tip='temperatura',
            unitate='C',
            api_key='c' * 64,
        )
        sensor_b = Senzor(
            tenant_id=tenant_b.id,
            element_bim_id=element_b.id,
            cod='T113-S-B',
            nume='Senzor B',
            tip='temperatura',
            unitate='C',
            api_key='b' * 64,
        )
        db.session.add_all([sensor_a, sensor_a_legacy, sensor_b])
        db.session.commit()

        db.session.add_all([
            SensorReading(
                tenant_id=tenant_a.id,
                senzor_id=sensor_a.id,
                ts=datetime.utcnow(),
                valoare=22,
            ),
            SensorReading(
                tenant_id=tenant_b.id,
                senzor_id=sensor_b.id,
                ts=datetime.utcnow(),
                valoare=30,
            ),
            SensorAlert(
                tenant_id=tenant_a.id,
                senzor_id=sensor_a.id,
                tip='peste_max',
                severitate='medie',
                valoare=22,
                mesaj='T113 alert A',
                status='noua',
            ),
            SensorAlert(
                tenant_id=tenant_b.id,
                senzor_id=sensor_b.id,
                tip='peste_max',
                severitate='medie',
                valoare=30,
                mesaj='T113 alert B',
                status='noua',
            ),
        ])
        db.session.commit()

        db.session.add_all([
            ExternalMapping(
                tenant_id=tenant_a.id,
                entity_type='element_bim',
                entity_id=element_a.id,
                source_system='manual',
                extern_id='T113-EXT-A',
            ),
            ExternalMapping(
                tenant_id=None,
                entity_type='element_bim',
                entity_id=element_a.id,
                source_system='manual',
                extern_id='T113-EXT-A-LEGACY',
            ),
            ExternalMapping(
                tenant_id=tenant_b.id,
                entity_type='element_bim',
                entity_id=element_b.id,
                source_system='manual',
                extern_id='T113-EXT-B',
            ),
        ])

        token_a = _token(tenant_a.id, user_a.id, 'T113 Token A', '1' * 64)
        token_b = _token(tenant_b.id, user_b.id, 'T113 Token B', '2' * 64)
        token_mismatch = _token(tenant_b.id, user_a.id, 'T113 Token Mismatch', '3' * 64)
        db.session.add_all([token_a, token_b, token_mismatch])
        db.session.add_all([
            AuditLog(
                tenant_id=tenant_a.id,
                user_id=user_a.id,
                entity_type='t113_audit_a',
                action='create',
            ),
            AuditLog(
                tenant_id=None,
                user_id=user_a.id,
                entity_type='t113_audit_legacy_a',
                action='create',
            ),
            AuditLog(
                tenant_id=tenant_b.id,
                user_id=user_b.id,
                entity_type='t113_audit_b',
                action='create',
            ),
        ])
        db.session.commit()

        return {
            'tenant_a': tenant_a.id,
            'tenant_b': tenant_b.id,
            'user_a': user_a.id,
            'proiect_a': proiect_a.id,
            'locatie_b': locatie_b.id,
            'sensor_a': sensor_a.id,
            'sensor_b': sensor_b.id,
            'alert_b': SensorAlert.query.filter_by(senzor_id=sensor_b.id).first().id,
            'mapping_b': ExternalMapping.query.filter_by(extern_id='T113-EXT-B').first().id,
            'token_a': token_a.id,
            'token_b': token_b.id,
            'token_a_plain': token_a.token,
            'token_mismatch_plain': token_mismatch.token,
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


def _curata_date(app):
    from models import (
        ApiToken, AuditLog, Cladire, ElementBIM, ExternalMapping, LocatieProiect,
        ModelBIM, Proiect, Santier, SensorAlert, SensorReading, Senzor,
        Tenant, Utilizator, db,
    )

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        for cls in (
            AuditLog, SensorAlert, SensorReading, Senzor, ExternalMapping,
            ElementBIM, ModelBIM, Cladire, Santier, LocatieProiect, ApiToken,
        ):
            for obj in cls.query.all():
                marker = (
                    getattr(obj, 'nume', '')
                    or getattr(obj, 'cod', '')
                    or getattr(obj, 'entity_type', '')
                    or ''
                )
                if str(marker).startswith('T113') or cls in (
                    AuditLog, SensorAlert, SensorReading, ExternalMapping,
                ):
                    db.session.delete(obj)
        for user in Utilizator.query.filter(Utilizator.email.like('t113_unit_%')).all():
            db.session.delete(user)
        for proiect in Proiect.query.filter(Proiect.cod_proiect.like('T113-UNIT-%')).all():
            db.session.delete(proiect)
        for tenant in Tenant.query.filter(Tenant.cod.like('test-t113-unit-%')).all():
            db.session.delete(tenant)
        db.session.commit()
