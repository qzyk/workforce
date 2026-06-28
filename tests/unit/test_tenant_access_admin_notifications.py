"""Teste pentru tenant access admin/notificari/realtime."""

from datetime import datetime

import pytest
from flask import g
from flask_login import login_user
from werkzeug.exceptions import HTTPException


@pytest.fixture(autouse=True)
def curata_admin_notif_tenant_access(app):
    _curata_date(app)
    yield
    _curata_date(app)


def test_query_users_for_tenant_strict_returneaza_doar_tenantul(app):
    from models import Utilizator
    from services.security.tenant_access import query_users_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        emails = {
            u.email for u in query_users_for_tenant()
            .filter(Utilizator.email.like('ta-admin-%@test.local')).all()
        }

    assert emails == {'ta-admin-a@test.local', 'ta-admin-conflict@test.local'}


def test_get_user_or_404_blocheaza_user_strain(app):
    from services.security.tenant_access import get_user_or_404

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        with pytest.raises(HTTPException) as exc:
            get_user_or_404(ids['user_b'])

    assert exc.value.code == 404


def test_query_notifications_for_tenant_filtreaza_destinatar_si_tenant(app):
    from models import NotificareApp
    from services.security.tenant_access import query_notifications_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        titluri = {
            n.titlu for n in query_notifications_for_tenant()
            .filter(NotificareApp.titlu.like('TA Admin%')).all()
        }

    assert titluri == {'TA Admin A', 'TA Admin Legacy A'}


def test_get_notification_or_404_blocheaza_notificare_straina(app):
    from services.security.tenant_access import get_notification_or_404

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        with pytest.raises(HTTPException) as exc:
            get_notification_or_404(ids['notif_b'])

    assert exc.value.code == 404


def test_query_presence_for_tenant_filtreaza_si_conflictul(app):
    from models import UserPresence
    from services.security.tenant_access import query_presence_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        users = {
            p.user_id for p in query_presence_for_tenant()
            .filter(UserPresence.user_id.in_([
                ids['user_a'], ids['user_b'], ids['user_conflict'],
            ])).all()
        }

    assert users == {ids['user_a']}


def test_query_realtime_events_for_tenant_filtreaza_si_conflictul(app):
    from models import RealtimeEvent
    from services.security.tenant_access import query_realtime_events_for_tenant

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        g.tenant_override = ids['tenant_a']

        tipuri = {
            e.event_type for e in query_realtime_events_for_tenant()
            .filter(RealtimeEvent.event_type.like('ta_admin_%')).all()
        }

    assert tipuri == {'ta_admin_a'}


def test_require_super_admin_for_global_scope_blocheaza_tenant_admin(app):
    from models import Utilizator
    from services.security.tenant_access import require_super_admin_for_global_scope

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        login_user(Utilizator.query.get(ids['user_a']))

        with pytest.raises(HTTPException) as exc:
            require_super_admin_for_global_scope()

    assert exc.value.code == 403


def test_require_super_admin_for_global_scope_permite_admin_fara_tenant(app):
    from models import Utilizator
    from services.security.tenant_access import require_super_admin_for_global_scope

    ids = _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'strict'
        login_user(Utilizator.query.get(ids['super_admin']))

        assert require_super_admin_for_global_scope() is True


def test_mode_off_pastreaza_query_nefiltrat(app):
    from models import NotificareApp, Utilizator
    from services.security.tenant_access import query_notifications_for_tenant, query_users_for_tenant

    _creeaza_date(app)

    with app.test_request_context('/'):
        app.config['MULTI_TENANT_MODE'] = 'off'

        users = query_users_for_tenant().filter(Utilizator.email.like('ta-admin-%@test.local')).count()
        notificari = query_notifications_for_tenant().filter(
            NotificareApp.titlu.like('TA Admin%')
        ).count()

    assert users == 4
    assert notificari == 4


def _creeaza_date(app):
    from models import (
        NotificareApp, Proiect, RealtimeEvent, Tenant, UserPresence,
        Utilizator, db,
    )

    with app.app_context():
        tenant_a = Tenant(cod='test-ta-admin-a', nume='Tenant Admin A')
        tenant_b = Tenant(cod='test-ta-admin-b', nume='Tenant Admin B')
        db.session.add_all([tenant_a, tenant_b])
        db.session.commit()

        user_a = _user('ta-admin-a@test.local', tenant_a.id)
        user_b = _user('ta-admin-b@test.local', tenant_b.id)
        user_conflict = _user('ta-admin-conflict@test.local', tenant_a.id)
        super_admin = _user('ta-admin-super@test.local', None)
        db.session.add_all([user_a, user_b, user_conflict, super_admin])
        db.session.commit()

        proiect_a = Proiect(
            tenant_id=tenant_a.id,
            cod_proiect='TA-ADMIN-PA',
            nume='TA Admin Project A',
            data_start=datetime.utcnow().date(),
            status='activ',
        )
        proiect_b = Proiect(
            tenant_id=tenant_b.id,
            cod_proiect='TA-ADMIN-PB',
            nume='TA Admin Project B',
            data_start=datetime.utcnow().date(),
            status='activ',
        )
        db.session.add_all([proiect_a, proiect_b])
        db.session.commit()

        notif_a = NotificareApp(
            tenant_id=tenant_a.id,
            utilizator_id=user_a.id,
            tip='generic',
            titlu='TA Admin A',
        )
        notif_legacy_a = NotificareApp(
            tenant_id=None,
            utilizator_id=user_a.id,
            tip='generic',
            titlu='TA Admin Legacy A',
        )
        notif_b = NotificareApp(
            tenant_id=tenant_b.id,
            utilizator_id=user_b.id,
            tip='generic',
            titlu='TA Admin B',
        )
        notif_conflict = NotificareApp(
            tenant_id=tenant_b.id,
            utilizator_id=user_a.id,
            tip='generic',
            titlu='TA Admin Conflict',
        )
        db.session.add_all([notif_a, notif_legacy_a, notif_b, notif_conflict])

        db.session.add_all([
            UserPresence(tenant_id=tenant_a.id, user_id=user_a.id, user_nume='A'),
            UserPresence(tenant_id=tenant_b.id, user_id=user_b.id, user_nume='B'),
            UserPresence(tenant_id=tenant_b.id, user_id=user_conflict.id, user_nume='Conflict'),
            RealtimeEvent(
                tenant_id=tenant_a.id,
                proiect_id=proiect_a.id,
                user_id=user_a.id,
                event_type='ta_admin_a',
            ),
            RealtimeEvent(
                tenant_id=tenant_b.id,
                proiect_id=proiect_b.id,
                user_id=user_b.id,
                event_type='ta_admin_b',
            ),
            RealtimeEvent(
                tenant_id=tenant_b.id,
                proiect_id=proiect_a.id,
                user_id=user_a.id,
                event_type='ta_admin_conflict',
            ),
        ])
        db.session.commit()

        return {
            'tenant_a': tenant_a.id,
            'tenant_b': tenant_b.id,
            'user_a': user_a.id,
            'user_b': user_b.id,
            'user_conflict': user_conflict.id,
            'super_admin': super_admin.id,
            'notif_b': notif_b.id,
        }


def _user(email, tenant_id):
    from models import Utilizator

    user = Utilizator(
        tenant_id=tenant_id,
        nume='TA',
        prenume='Admin',
        email=email,
        rol='admin',
        activ=True,
    )
    user.set_password('test_pass_123')
    return user


def _curata_date(app):
    from models import (
        NotificareApp, Proiect, RealtimeEvent, Tenant, UserPresence,
        Utilizator, db,
    )

    with app.app_context():
        app.config['MULTI_TENANT_MODE'] = 'off'

        RealtimeEvent.query.filter(RealtimeEvent.event_type.like('ta_admin_%')).delete(synchronize_session=False)
        UserPresence.query.filter(
            UserPresence.user.has(Utilizator.email.like('ta-admin-%@test.local'))
        ).delete(synchronize_session=False)
        NotificareApp.query.filter(NotificareApp.titlu.like('TA Admin%')).delete(synchronize_session=False)
        Proiect.query.filter(Proiect.cod_proiect.like('TA-ADMIN-%')).delete(synchronize_session=False)
        Utilizator.query.filter(Utilizator.email.like('ta-admin-%@test.local')).delete(synchronize_session=False)
        Tenant.query.filter(Tenant.cod.like('test-ta-admin-%')).delete(synchronize_session=False)

        for user in Utilizator.query.filter(Utilizator.email.in_([
            'admin_test@test.local',
            'operator_test@test.local',
        ])).all():
            user.tenant_id = None

        db.session.commit()
