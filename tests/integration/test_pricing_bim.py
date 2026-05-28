"""Faza 2 auto-pricing: catalog 2026 + generare preturi pe elemente BIM."""
from decimal import Decimal


def _user(app):
    from models import db, Utilizator
    u = Utilizator.query.filter_by(email='pricing@test.local').first()
    if not u:
        u = Utilizator(nume='P', prenume='R', email='pricing@test.local', rol='admin', activ=True)
        u.set_password('x'); db.session.add(u); db.session.commit()
    return u


class TestPricingService:
    def test_seed_catalog_idempotent(self, app):
        from services import pricing_bim
        from models import PretReferinta
        with app.app_context():
            n1 = pricing_bim.seed_catalog(tenant_id=None)
            n2 = pricing_bim.seed_catalog(tenant_id=None)  # a doua oara: 0
            assert n1 > 0 and n2 == 0
            assert PretReferinta.query.filter_by(categorie_lucrare='beton', um='mc').first() is not None

    def test_categorie_si_um(self, app):
        from services import pricing_bim
        from models import ElementBIM
        with app.app_context():
            beam = ElementBIM(cod='B', tip_element='beam', material='Beton C25/30', unitate_masura='mc')
            rebar = ElementBIM(cod='R', tip_element='reinforcingbar', material='BST500s', unitate_masura='kg')
            steel = ElementBIM(cod='S', tip_element='beam', material='S355', unitate_masura='kg')
            assert pricing_bim.categorie_si_um(beam) == ('beton', 'mc')
            assert pricing_bim.categorie_si_um(rebar) == ('armatura', 'kg')
            assert pricing_bim.categorie_si_um(steel) == ('confectii_metalice', 'kg')

    def test_genereaza_preturi_totaluri(self, app):
        from models import db, Santier, Cladire, ElementBIM
        from services import pricing_bim
        with app.app_context():
            u = _user(app)
            s = Santier(cod='PRJ-PR', nume='Pricing'); db.session.add(s); db.session.flush()
            c = Cladire(santier_id=s.id, cod='C1', nume='C1'); db.session.add(c); db.session.flush()
            db.session.add_all([
                ElementBIM(cladire_id=c.id, cod='B1', tip_element='beam',
                           material='Beton C25/30', cantitate=Decimal('10'), unitate_masura='mc'),
                ElementBIM(cladire_id=c.id, cod='S1', tip_element='slab',
                           material='Beton C25/30', cantitate=Decimal('20'), unitate_masura='mc'),
                ElementBIM(cladire_id=c.id, cod='R1', tip_element='reinforcingbar',
                           material='BST500s', cantitate=Decimal('1000'), unitate_masura='kg'),
            ])
            db.session.commit()
            res = pricing_bim.genereaza_preturi_santier(s.id, u)
            assert res['status'] == 'ok'
            assert res['nr_pretuite'] == 3
            # beton 30mc x750=22500 + armatura 1000kg x7.5=7500 = 30000
            assert res['total_fara_tva'] == 30000.0
            assert res['tva'] == 6300.0
            assert res['total_cu_tva'] == 36300.0

    def test_idempotent_rerun(self, app):
        """A doua rulare nu dubleaza cost-urile."""
        from models import db, Santier, Cladire, ElementBIM, BIMCostItem
        from services import pricing_bim
        with app.app_context():
            u = _user(app)
            s = Santier(cod='PRJ-PR2', nume='P2'); db.session.add(s); db.session.flush()
            c = Cladire(santier_id=s.id, cod='C', nume='C'); db.session.add(c); db.session.flush()
            db.session.add(ElementBIM(cladire_id=c.id, cod='B', tip_element='beam',
                                      material='Beton C25/30', cantitate=Decimal('5'), unitate_masura='mc'))
            db.session.commit()
            pricing_bim.genereaza_preturi_santier(s.id, u)
            pricing_bim.genereaza_preturi_santier(s.id, u)
            el = ElementBIM.query.filter_by(cod='B').first()
            n = BIMCostItem.query.filter_by(element_bim_id=el.id,
                                            referinta_extern='auto-pricing-2026').count()
            assert n == 1


class TestPricingRoutes:
    def test_catalog_page(self, authenticated_client):
        r = authenticated_client.get('/bim/preturi')
        assert r.status_code == 200
        assert b'beton' in r.data

    def test_genereaza_flag_off_redirect(self, app, authenticated_client):
        from models import db, Santier
        with app.app_context():
            s = Santier(cod='PRJ-FLG', nume='F'); db.session.add(s); db.session.commit()
            sid = s.id
        from services.feature_flags import set_flag
        with app.app_context():
            set_flag('bim-auto-pricing', False, commit=True)
        r = authenticated_client.post(f'/bim/santier/{sid}/genereaza-preturi', follow_redirects=False)
        assert r.status_code in (302, 303)
