"""Teste route-level pentru T1.11 admin/notificari."""

from datetime import datetime

import pytest


@pytest.fixture(autouse=True)
def curata_admin_notif_routes(app):
    _curata_date(app)
    yield
    _curata_date(app)


def test_mode_off_admin_si_tenant_routes_ramane_legacy(authenticated_client, app):
    _creeaza_date(app)
    app.config['MULTI_TENANT_MODE'] = 'off'

    users = authenticated_client.get('/setari/utilizatori')
    tenants = authenticated_client.get('/admin/tenants/')

    assert users.status_code == 200
    assert tenants.status_code == 200


def test_strict_tenant_admin_vede_doar_userii_tenantului(authenticated_client, app, admin_user):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.get('/setari/utilizatori')

    assert raspuns.status_code == 200
    assert b'ta-route-a@test.local' in raspuns.data
    assert b'ta-route-b@test.local' not in raspuns.data


def test_strict_tenant_admin_nu_editeaza_user_strain(authenticated_client, app, admin_user):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    edit = authenticated_client.get(f'/setari/utilizatori/{ids["user_b"]}/editeaza')
    reset = authenticated_client.post(
        f'/setari/utilizatori/{ids["user_b"]}/reset-parola',
        data={'parola_noua': 'new_pass_123'},
    )
    toggle = authenticated_client.post(f'/setari/utilizatori/{ids["user_b"]}/toggle-status')

    assert edit.status_code == 404
    assert reset.status_code == 404
    assert toggle.status_code == 404


def test_strict_creare_user_admin_primeste_tenantul_curent(authenticated_client, app, admin_user):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.post('/setari/utilizatori/adauga', data={
        'nume': 'Nou',
        'prenume': 'Tenant',
        'email': 'ta-route-new@test.local',
        'parola': 'test_pass_123',
        'rol': 'operator',
    })

    assert raspuns.status_code == 302
    with app.app_context():
        from models import Utilizator

        user = Utilizator.query.filter_by(email='ta-route-new@test.local').one()
        assert user.tenant_id == ids['tenant_a']


def test_strict_tenant_admin_nu_acceseaza_backup_global(authenticated_client, app, admin_user):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    backup = authenticated_client.get('/setari/backup')
    download = authenticated_client.get('/setari/backup/test.zip/descarca')

    assert backup.status_code == 403
    assert download.status_code == 403


def test_strict_super_admin_poate_accesa_backup_si_tenants(authenticated_client, app, admin_user):
    _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, None)
    app.config['MULTI_TENANT_MODE'] = 'strict'

    backup = authenticated_client.get('/setari/backup')
    tenants = authenticated_client.get('/admin/tenants/')

    assert backup.status_code == 200
    assert tenants.status_code == 200


def test_optional_tenant_admin_nu_acceseaza_tenant_management(authenticated_client, app, admin_user):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'optional'

    raspuns = authenticated_client.get('/admin/tenants/')

    assert raspuns.status_code == 403


def test_strict_info_sistem_este_scopat_pe_tenant(authenticated_client, app, admin_user):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'

    raspuns = authenticated_client.get('/setari/info-sistem')

    assert raspuns.status_code == 200
    assert raspuns.json['utilizatori'] == 2  # admin fixture + user A
    assert raspuns.json['proiecte'] == 1


def test_strict_notificari_count_exclude_notificari_straine_si_conflict(
    authenticated_client, app, admin_user
):
    ids = _creeaza_date(app)
    _seteaza_tenant_user(app, admin_user.id, ids['tenant_a'])
    app.config['MULTI_TENANT_MODE'] = 'strict'
    _seteaza_contract_flag(app, True)

    count = authenticated_client.get('/contracte/notificari/count')
    mark_conflict = authenticated_client.post(
        f'/contracte/notificari/{ids["notif_conflict"]}/mark-read'
    )

    assert count.status_code == 200
    assert count.json['count'] == 1
    assert mark_conflict.status_code in (302, 303)
    with app.app_context():
        from models import NotificareApp

        assert NotificareApp.query.get(ids['notif_conflict']).citita is False


def test_strict_realtime_si_presence_servicii_sunt_scopate(app):
    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        from flask import g
        from services import presence, realtime

        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        active = presence.get_active_users()
        events = realtime.get_events_since(0)

    assert {p.user_id for p in active} == {ids['user_a']}
    assert {e.event_type for e in events} == {'ta_route_event_a'}


def _creeaza_date(app):
    from models import (
        NotificareApp, Proiect, RealtimeEvent, Tenant, UserPresence,
        Utilizator, db,
    )

    with app.app_context():
        tenant_a = Tenant(cod='test-ta-route-admin-a', nume='Tenant Route Admin A')
        tenant_b = Tenant(cod='test-ta-route-admin-b', nume='Tenant Route Admin B')
        db.session.add_all([tenant_a, tenant_b])
        db.session.commit()

        admin_fixture = Utilizator.query.filter_by(email='admin_test@test.local').first()
        if admin_fixture:
            admin_fixture.tenant_id = tenant_a.id

        user_a = _user('ta-route-a@test.local', tenant_a.id)
        user_b = _user('ta-route-b@test.local', tenant_b.id)
        db.session.add_all([user_a, user_b])
        db.session.commit()

        proiect_a = Proiect(
            tenant_id=tenant_a.id,
            cod_proiect='TA-ROUTE-ADMIN-A',
            nume='TA Route Admin A',
            data_start=datetime.utcnow().date(),
            status='activ',
        )
        proiect_b = Proiect(
            tenant_id=tenant_b.id,
            cod_proiect='TA-ROUTE-ADMIN-B',
            nume='TA Route Admin B',
            data_start=datetime.utcnow().date(),
            status='activ',
        )
        db.session.add_all([proiect_a, proiect_b])
        db.session.commit()

        notif_ok = NotificareApp(
            tenant_id=tenant_a.id,
            utilizator_id=admin_fixture.id,
            tip='generic',
            titlu='TA Route Notif A',
            citita=False,
        )
        notif_conflict = NotificareApp(
            tenant_id=tenant_b.id,
            utilizator_id=admin_fixture.id,
            tip='generic',
            titlu='TA Route Notif Conflict',
            citita=False,
        )
        db.session.add_all([notif_ok, notif_conflict])
        db.session.add_all([
            UserPresence(tenant_id=tenant_a.id, user_id=user_a.id, user_nume='A'),
            UserPresence(tenant_id=tenant_b.id, user_id=user_b.id, user_nume='B'),
            RealtimeEvent(
                tenant_id=tenant_a.id,
                proiect_id=proiect_a.id,
                user_id=user_a.id,
                event_type='ta_route_event_a',
            ),
            RealtimeEvent(
                tenant_id=tenant_b.id,
                proiect_id=proiect_b.id,
                user_id=user_b.id,
                event_type='ta_route_event_b',
            ),
        ])
        db.session.commit()

        return {
            'tenant_a': tenant_a.id,
            'tenant_b': tenant_b.id,
            'user_a': user_a.id,
            'user_b': user_b.id,
            'notif_conflict': notif_conflict.id,
        }


def _user(email, tenant_id):
    from models import Utilizator

    user = Utilizator(
        tenant_id=tenant_id,
        nume='TA',
        prenume='Route',
        email=email,
        rol='operator',
        activ=True,
    )
    user.set_password('test_pass_123')
    return user


def _seteaza_tenant_user(app, user_id, tenant_id):
    from models import Utilizator, db

    with app.app_context():
        user = db.session.get(Utilizator, user_id)
        user.tenant_id = tenant_id
        db.session.commit()


def _seteaza_contract_flag(app, enabled):
    from services.feature_flags import set_flag

    with app.app_context():
        set_flag('controale-contract', enabled, commit=True)


def _curata_date(app):
    from models import (
        NotificareApp, Proiect, RealtimeEvent, Tenant, UserPresence,
        Utilizator, db,
    )

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'
        from services.feature_flags import set_flag
        set_flag('controale-contract', False, commit=False)

        RealtimeEvent.query.filter(RealtimeEvent.event_type.like('ta_route_event_%')).delete(synchronize_session=False)
        UserPresence.query.filter(
            UserPresence.user.has(Utilizator.email.like('ta-route-%@test.local'))
        ).delete(synchronize_session=False)
        NotificareApp.query.filter(NotificareApp.titlu.like('TA Route Notif%')).delete(synchronize_session=False)
        Proiect.query.filter(Proiect.cod_proiect.like('TA-ROUTE-ADMIN-%')).delete(synchronize_session=False)
        Utilizator.query.filter(Utilizator.email.like('ta-route-%@test.local')).delete(synchronize_session=False)
        Utilizator.query.filter_by(email='ta-route-new@test.local').delete(synchronize_session=False)
        Tenant.query.filter(Tenant.cod.like('test-ta-route-admin-%')).delete(synchronize_session=False)

        for user in Utilizator.query.filter(Utilizator.email.in_([
            'admin_test@test.local',
            'operator_test@test.local',
        ])).all():
            user.tenant_id = None

        db.session.commit()
