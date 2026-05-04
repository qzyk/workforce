"""
Unit tests pentru multi-tenant infrastructure (tenant.py).
"""

import pytest


class TestTenantMode:
    def test_default_mode_e_off(self, app):
        from tenant import get_mode, MODE_OFF
        with app.app_context():
            assert get_mode() == MODE_OFF

    def test_mode_optional(self, app):
        from tenant import get_mode, MODE_OPTIONAL
        with app.app_context():
            app.config['MULTI_TENANT_MODE'] = 'optional'
            try:
                assert get_mode() == MODE_OPTIONAL
            finally:
                app.config['MULTI_TENANT_MODE'] = 'off'


class TestTenantContextResolution:
    def test_no_tenant_when_unauthenticated(self, app):
        from tenant import get_current_tenant_id
        with app.test_request_context('/'):
            assert get_current_tenant_id() is None

    def test_tenant_from_session(self, app):
        from tenant import get_current_tenant_id
        from flask import session
        with app.test_request_context('/'):
            session['tenant_id'] = 42
            assert get_current_tenant_id() == 42

    def test_tenant_override_takes_precedence(self, app):
        from tenant import get_current_tenant_id
        from flask import g, session
        with app.test_request_context('/'):
            g.tenant_override = 99
            session['tenant_id'] = 42
            assert get_current_tenant_id() == 99


class TestTenantScopeFilter:
    def test_off_mode_no_filtering(self, app):
        """In MODE=off, with_tenant_scope returneaza query-ul intact."""
        from tenant import with_tenant_scope
        from models import db, Proiect
        with app.app_context():
            base_q = Proiect.query
            scoped_q = with_tenant_scope(base_q, Proiect)
            # Acelasi obiect (sau echivalent fara WHERE adaugat)
            assert str(base_q) == str(scoped_q)

    def test_strict_mode_filters_by_tenant(self, app):
        """In MODE=strict + tenant_id setat, query-ul are WHERE tenant_id = X."""
        from tenant import with_tenant_scope
        from models import db, Proiect, Tenant
        from flask import g
        with app.app_context():
            app.config['MULTI_TENANT_MODE'] = 'strict'
            try:
                # Cleanup
                Tenant.query.filter_by(cod='test-scope').delete()
                Proiect.query.filter(Proiect.cod_proiect.like('TS-%')).delete()
                db.session.commit()
                t = Tenant(cod='test-scope', nume='Scope Test')
                db.session.add(t); db.session.commit()
                p1 = Proiect(cod_proiect='TS-T1', nume='In tenant',
                             data_start=__import__('datetime').date(2025,1,1),
                             status='activ', tenant_id=t.id)
                p2 = Proiect(cod_proiect='TS-NO', nume='Fara tenant',
                             data_start=__import__('datetime').date(2025,1,1),
                             status='activ', tenant_id=None)
                db.session.add(p1); db.session.add(p2); db.session.commit()

                with app.test_request_context('/'):
                    g.tenant_override = t.id
                    scoped = with_tenant_scope(Proiect.query, Proiect).all()
                    cods = [p.cod_proiect for p in scoped]
                    assert 'TS-T1' in cods
                    assert 'TS-NO' not in cods

                # Cleanup
                Proiect.query.filter(Proiect.cod_proiect.like('TS-%')).delete()
                Tenant.query.filter_by(cod='test-scope').delete()
                db.session.commit()
            finally:
                app.config['MULTI_TENANT_MODE'] = 'off'


class TestTenantContextProcessor:
    def test_template_has_current_tenant_var(self, client):
        """Pagina login trebuie sa aiba var current_tenant disponibil (None default)."""
        resp = client.get('/auth/login')
        assert resp.status_code == 200


class TestTenantDecorators:
    def test_tenant_required_off_mode_pass(self, app):
        """In MODE=off, decoratorul lasa request-ul sa treaca."""
        from tenant import tenant_required
        with app.test_request_context('/'):
            @tenant_required
            def view():
                return 'ok'
            assert view() == 'ok'

    def test_tenant_required_strict_no_tenant_aborts(self, app):
        """In MODE=strict fara tenant -> abort 403."""
        from tenant import tenant_required
        from werkzeug.exceptions import HTTPException
        with app.test_request_context('/'):
            app.config['MULTI_TENANT_MODE'] = 'strict'
            try:
                @tenant_required
                def view():
                    return 'should not reach'
                with pytest.raises(HTTPException) as exc:
                    view()
                assert exc.value.code == 403
            finally:
                app.config['MULTI_TENANT_MODE'] = 'off'
