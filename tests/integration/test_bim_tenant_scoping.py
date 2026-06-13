"""
Integration tests pentru tenant scoping pe query-urile BIM (Faza bim-1).

Aplicam helperul EXISTENT tenant.with_tenant_scope pe:
- clash_lista (ClashRun)
- rules_lista (BIMRule)
- sensors_lista (Senzor)
- get_published_versions_for_santier (BIMModelVersion)

Verificam:
- mod 'strict': tenant A nu vede clash/regula/senzor ale lui B
- mod 'off' (default): comportament IDENTIC (helperul nu filtreaza) - regresie

Folosim helperul direct (deterministic) + un test de regresie la nivel de ruta.
"""

import secrets
import pytest

from flask import g
from models import db, BIMRule, ClashRun, Senzor, Tenant, BIMModelVersion, ModelBIM


def _mk_tenant(cod):
    t = Tenant.query.filter_by(cod=cod).first()
    if not t:
        t = Tenant(cod=cod, nume=cod.upper())
        db.session.add(t)
        db.session.commit()
    return t


def _mk_rule(cod, tenant_id):
    r = BIMRule(cod=cod, nume=cod, tip='required_properties',
                definitie_json='{}', tenant_id=tenant_id)
    db.session.add(r)
    return r


def _mk_clash(tenant_id):
    c = ClashRun(tip='mixed', status='finalizat', tenant_id=tenant_id)
    db.session.add(c)
    return c


def _mk_senzor(cod, tenant_id):
    s = Senzor(cod=cod, nume=cod, tip='temperatura', unitate='C',
               api_key=secrets.token_hex(32), tenant_id=tenant_id)
    db.session.add(s)
    return s


# ====================================================
# Helper direct: strict filtreaza, off nu
# ====================================================

class TestTenantScopeStrict:
    def test_strict_clash_izolat_pe_tenant(self, app):
        from tenant import with_tenant_scope
        with app.app_context():
            app.config['MULTI_TENANT_MODE'] = 'strict'
            try:
                ta = _mk_tenant('test-tA')
                tb = _mk_tenant('test-tB')
                _mk_clash(ta.id)
                _mk_clash(tb.id)
                db.session.commit()
                ta_id = ta.id

                with app.test_request_context('/'):
                    g.tenant_override = ta_id
                    runs = with_tenant_scope(ClashRun.query, ClashRun).all()
                    assert len(runs) == 1
                    assert all(r.tenant_id == ta_id for r in runs)
            finally:
                app.config['MULTI_TENANT_MODE'] = 'off'

    def test_strict_rule_izolat_pe_tenant(self, app):
        from tenant import with_tenant_scope
        with app.app_context():
            app.config['MULTI_TENANT_MODE'] = 'strict'
            try:
                ta = _mk_tenant('test-tA')
                tb = _mk_tenant('test-tB')
                _mk_rule('R-A', ta.id)
                _mk_rule('R-B', tb.id)
                db.session.commit()
                ta_id = ta.id

                with app.test_request_context('/'):
                    g.tenant_override = ta_id
                    rules = with_tenant_scope(BIMRule.query, BIMRule).all()
                    cods = {r.cod for r in rules}
                    assert cods == {'R-A'}
            finally:
                app.config['MULTI_TENANT_MODE'] = 'off'

    def test_strict_senzor_izolat_pe_tenant(self, app):
        from tenant import with_tenant_scope
        with app.app_context():
            app.config['MULTI_TENANT_MODE'] = 'strict'
            try:
                ta = _mk_tenant('test-tA')
                tb = _mk_tenant('test-tB')
                _mk_senzor('SENS-A', ta.id)
                _mk_senzor('SENS-B', tb.id)
                db.session.commit()
                tb_id = tb.id

                with app.test_request_context('/'):
                    g.tenant_override = tb_id
                    senzori = with_tenant_scope(Senzor.query, Senzor).all()
                    cods = {s.cod for s in senzori}
                    assert cods == {'SENS-B'}
            finally:
                app.config['MULTI_TENANT_MODE'] = 'off'

    def test_strict_published_versions_izolat(self, app):
        """get_published_versions_for_santier filtreaza pe tenant in mod strict."""
        from services import bim_workflow
        with app.app_context():
            app.config['MULTI_TENANT_MODE'] = 'strict'
            try:
                ta = _mk_tenant('test-tA')
                tb = _mk_tenant('test-tB')
                # Un singur santier (ModelBIM legat de santier prin santier_id)
                from models import Santier
                s = Santier(cod='S-TEN', nume='Tenant santier')
                db.session.add(s); db.session.commit()
                m = ModelBIM(nume='M-TEN', tip='ifc', santier_id=s.id)
                db.session.add(m); db.session.commit()
                # 2 versiuni published, tenant-uri diferite
                va = BIMModelVersion(model_id=m.id, versiune='vA', status='published',
                                     tenant_id=ta.id)
                vb = BIMModelVersion(model_id=m.id, versiune='vB', status='published',
                                     tenant_id=tb.id)
                db.session.add(va); db.session.add(vb); db.session.commit()
                sid, ta_id = s.id, ta.id

                with app.test_request_context('/'):
                    g.tenant_override = ta_id
                    versiuni = bim_workflow.get_published_versions_for_santier(sid)
                    versiuni_str = {v.versiune for v in versiuni}
                    assert versiuni_str == {'vA'}
            finally:
                app.config['MULTI_TENANT_MODE'] = 'off'


# ====================================================
# Mod off: regresie - comportament neschimbat (vede tot)
# ====================================================

class TestTenantScopeOffRegresie:
    def test_off_clash_vede_tot(self, app):
        from tenant import with_tenant_scope
        with app.app_context():
            # MODE = off (default)
            ta = _mk_tenant('test-tA')
            tb = _mk_tenant('test-tB')
            _mk_clash(ta.id)
            _mk_clash(tb.id)
            db.session.commit()
            ta_id = ta.id
            with app.test_request_context('/'):
                g.tenant_override = ta_id
                runs = with_tenant_scope(ClashRun.query, ClashRun).all()
                # In off, NU filtreaza: vede ambele
                assert len(runs) == 2

    def test_off_query_identic_cu_query_brut(self, app):
        """In MODE=off helperul returneaza acelasi SQL ca query-ul brut (zero filtru)."""
        from tenant import with_tenant_scope
        with app.app_context():
            base = BIMRule.query
            scoped = with_tenant_scope(BIMRule.query, BIMRule)
            assert str(base) == str(scoped)


# ====================================================
# Regresie la nivel de ruta: in mod off, listele BIM raspund 200 normal
# ====================================================

class TestRuteBimModOff:
    def test_rules_lista_off_mode_ok(self, authenticated_client, app):
        from services import feature_flags as ff
        with app.app_context():
            ff.set_flag('bim-rule-engine', True)
            _mk_rule('R-OFF-1', None)
            db.session.commit()
        resp = authenticated_client.get('/bim/rules')
        assert resp.status_code == 200

    def test_clash_lista_off_mode_ok(self, authenticated_client, app):
        from services import feature_flags as ff
        with app.app_context():
            ff.set_flag('bim-clash-detection', True)
            _mk_clash(None)
            db.session.commit()
        resp = authenticated_client.get('/bim/clash')
        assert resp.status_code == 200

    def test_sensors_lista_off_mode_ok(self, authenticated_client, app):
        from services import feature_flags as ff
        with app.app_context():
            ff.set_flag('bim-iot-sensors', True)
            _mk_senzor('SENS-OFF-1', None)
            db.session.commit()
        resp = authenticated_client.get('/bim/sensors')
        assert resp.status_code == 200
