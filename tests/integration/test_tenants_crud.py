"""
Integration tests pentru CRUD tenants + admin permissions.
"""

import pytest


class TestTenantsCrud:
    def test_lista_redirect_unauthenticated(self, client):
        resp = client.get('/admin/tenants/', follow_redirects=False)
        assert resp.status_code in (302, 401)

    def test_lista_admin_can_access(self, authenticated_client):
        resp = authenticated_client.get('/admin/tenants/')
        assert resp.status_code == 200
        assert b'Tenant Management' in resp.data

    def test_lista_operator_blocked(self, operator_client):
        resp = operator_client.get('/admin/tenants/', follow_redirects=False)
        assert resp.status_code in (302, 403)

    def test_creare_tenant(self, app, authenticated_client):
        from models import db, Tenant
        with app.app_context():
            Tenant.query.filter_by(cod='test-crud').delete()
            db.session.commit()

        resp = authenticated_client.post('/admin/tenants/nou', data={
            'cod': 'test-crud',
            'nume': 'Test CRUD Tenant',
            'activ': '1',
        }, follow_redirects=False)
        assert resp.status_code in (200, 302)

        with app.app_context():
            t = Tenant.query.filter_by(cod='test-crud').first()
            assert t is not None
            assert t.nume == 'Test CRUD Tenant'

    def test_cod_duplicate_blocked(self, app, authenticated_client):
        from models import db, Tenant
        with app.app_context():
            Tenant.query.filter_by(cod='test-dup').delete()
            db.session.commit()
            db.session.add(Tenant(cod='test-dup', nume='Existent'))
            db.session.commit()

        resp = authenticated_client.post('/admin/tenants/nou', data={
            'cod': 'test-dup',
            'nume': 'Duplicat',
        }, follow_redirects=True)
        # Trebuie sa dea flash error (status 200 cu pagina form)
        assert b'exista deja' in resp.data or b'duplicat' in resp.data.lower()

    def test_editeaza_tenant(self, app, authenticated_client):
        from models import db, Tenant
        with app.app_context():
            Tenant.query.filter_by(cod='test-edit').delete()
            db.session.commit()
            t = Tenant(cod='test-edit', nume='Inainte', activ=True)
            db.session.add(t); db.session.commit()
            tid = t.id

        resp = authenticated_client.post(f'/admin/tenants/{tid}/editeaza', data={
            'nume': 'Dupa modificare',
            'activ': '',  # uncheck
        })
        with app.app_context():
            t2 = Tenant.query.get(tid)
            assert t2.nume == 'Dupa modificare'
            assert t2.activ is False

    def test_sterge_tenant_fara_useri(self, app, authenticated_client):
        from models import db, Tenant
        with app.app_context():
            Tenant.query.filter_by(cod='test-del').delete()
            db.session.commit()
            t = Tenant(cod='test-del', nume='To delete')
            db.session.add(t); db.session.commit()
            tid = t.id

        resp = authenticated_client.post(f'/admin/tenants/{tid}/sterge')
        assert resp.status_code in (200, 302)

        with app.app_context():
            assert Tenant.query.get(tid) is None

    def test_sterge_blocat_daca_are_useri(self, app, authenticated_client):
        from models import db, Tenant, Utilizator
        with app.app_context():
            Tenant.query.filter_by(cod='test-with-users').delete()
            db.session.commit()
            t = Tenant(cod='test-with-users', nume='Has users')
            db.session.add(t); db.session.commit()
            u = Utilizator.query.filter_by(email='admin_test@test.local').first()
            old_tid = u.tenant_id
            u.tenant_id = t.id
            db.session.commit()
            tid = t.id

        try:
            resp = authenticated_client.post(f'/admin/tenants/{tid}/sterge', follow_redirects=True)
            # Tenant-ul ramane (nu poate fi sters daca are useri)
            with app.app_context():
                assert Tenant.query.get(tid) is not None
        finally:
            with app.app_context():
                u = Utilizator.query.filter_by(email='admin_test@test.local').first()
                u.tenant_id = old_tid
                db.session.commit()

    def test_atribuie_dezatribuie_user(self, app, authenticated_client):
        from models import db, Tenant, Utilizator
        with app.app_context():
            Tenant.query.filter_by(cod='test-assign').delete()
            db.session.commit()
            t = Tenant(cod='test-assign', nume='Assign')
            db.session.add(t); db.session.commit()
            tid = t.id
            # Foloseste operator user (creat prin fixture)
            u = Utilizator.query.filter_by(email='operator_test@test.local').first()
            if not u:
                u = Utilizator(nume='Op', prenume='Test', email='operator_test@test.local',
                              rol='operator', activ=True)
                u.set_password('p')
                db.session.add(u); db.session.commit()
            old_tid = u.tenant_id
            u.tenant_id = None
            db.session.commit()
            uid = u.id

        # Atribuie
        authenticated_client.post(f'/admin/tenants/{tid}/utilizatori/{uid}/atribuie')
        with app.app_context():
            u_after = Utilizator.query.get(uid)
            assert u_after.tenant_id == tid

        # Dezatribuie
        authenticated_client.post(f'/admin/tenants/{tid}/utilizatori/{uid}/dezatribuie')
        with app.app_context():
            u_after = Utilizator.query.get(uid)
            assert u_after.tenant_id is None

        # Cleanup
        with app.app_context():
            u_after = Utilizator.query.get(uid)
            u_after.tenant_id = old_tid
            db.session.commit()


class TestTenantUtilizatoriPage:
    def test_pagina_utilizatori_se_incarca(self, app, authenticated_client):
        from models import db, Tenant
        with app.app_context():
            Tenant.query.filter_by(cod='test-up').delete()
            db.session.commit()
            t = Tenant(cod='test-up', nume='Users page')
            db.session.add(t); db.session.commit()
            tid = t.id

        resp = authenticated_client.get(f'/admin/tenants/{tid}/utilizatori')
        assert resp.status_code == 200
        assert b'Utilizatori' in resp.data
