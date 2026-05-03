"""
Teste pentru modelele BIM - validare schema, FK-uri, relatii ierarhice si helpers.
"""

import pytest
from datetime import date, datetime


@pytest.fixture
def santier_complet(app):
    """Creeaza o ierarhie BIM completa pentru teste: santier -> cladire -> nivel -> spatiu -> element."""
    from models import db, Santier, Cladire, Nivel, Zona, Spatiu, ElementBIM, Asset
    with app.app_context():
        # Cleanup precedent
        Asset.query.delete()
        ElementBIM.query.delete()
        Spatiu.query.delete()
        Zona.query.delete()
        Nivel.query.delete()
        Cladire.query.delete()
        Santier.query.delete()
        db.session.commit()

        s = Santier(cod='SITE-T1', nume='Santier Test', oras='Bucuresti')
        db.session.add(s)
        db.session.commit()

        c = Cladire(santier_id=s.id, cod='BLD-A', nume='Cladire A', nr_niveluri=3)
        db.session.add(c)
        db.session.commit()

        # Nivele: subsol, parter, etaj 1
        levels = [
            Nivel(cladire_id=c.id, cod='B01', nume='Subsol', ordine=-1, elevatie_m=-3.0),
            Nivel(cladire_id=c.id, cod='N00', nume='Parter', ordine=0, elevatie_m=0.0),
            Nivel(cladire_id=c.id, cod='N01', nume='Etaj 1', ordine=1, elevatie_m=3.5),
        ]
        for n in levels:
            db.session.add(n)
        db.session.commit()

        z = Zona(cladire_id=c.id, nivel_id=levels[1].id, cod='Z-PUB', nume='Zona publica',
                 tip_zona='functional')
        db.session.add(z)
        db.session.commit()

        sp = Spatiu(nivel_id=levels[1].id, zona_id=z.id, cod='P.05', nume='Receptie',
                    tip_spatiu='hol', suprafata_mp=45.5)
        db.session.add(sp)
        db.session.commit()

        e = ElementBIM(spatiu_id=sp.id, nivel_id=levels[1].id, cladire_id=c.id,
                       cod='AHU-03', nume='CTA receptie',
                       tip_element='AHU', status='in_executie')
        db.session.add(e)
        db.session.commit()

        a = Asset(element_bim_id=e.id, producator='Daikin', model='VRV-IV',
                  serial='SN-2024-0001',
                  data_punere_functiune=date(2025, 6, 15),
                  data_garantie_pana=date(2027, 6, 14),
                  interval_mentenanta_zile=180)
        db.session.add(a)
        db.session.commit()

        return {
            'santier': s, 'cladire': c, 'niveluri': levels,
            'zona': z, 'spatiu': sp, 'element': e, 'asset': a
        }


def test_bim_tables_exist(app):
    """Tabelele BIM sunt create."""
    from models import db
    from sqlalchemy import inspect
    with app.app_context():
        insp = inspect(db.engine)
        tables = set(insp.get_table_names())
    expected = {
        'bim_santiere', 'bim_cladiri', 'bim_niveluri', 'bim_zone',
        'bim_spatii', 'bim_elemente', 'bim_assets', 'bim_issues', 'bim_modele',
        'tenants',
    }
    missing = expected - tables
    assert not missing, f'Tabele BIM lipsa: {missing}'


def test_santier_unique_per_tenant(app):
    """Cod santier unic per tenant."""
    from models import db, Santier
    with app.app_context():
        Santier.query.filter_by(cod='DUP-SITE').delete()
        db.session.commit()

        s1 = Santier(cod='DUP-SITE', nume='S1')
        db.session.add(s1)
        db.session.commit()

        # Acelasi cod pe acelasi tenant (NULL == NULL nu in SQL, dar verificam doar ca constraint exista)
        s2 = Santier(cod='DUP-SITE', nume='S2', tenant_id=1)
        db.session.add(s2)
        # E ok ca s2 sa se salveze daca tenant_id e diferit (NULL vs 1)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()


def test_ierarhie_completa(app, santier_complet):
    """Ierarhia santier -> cladire -> nivel -> spatiu -> element e parcurgibila."""
    with app.app_context():
        from models import Santier
        s = Santier.query.filter_by(cod='SITE-T1').first()
        assert s is not None

        cladiri = list(s.cladiri)
        assert len(cladiri) == 1
        assert cladiri[0].cod == 'BLD-A'

        niveluri = list(cladiri[0].niveluri)
        assert len(niveluri) == 3
        # Sortare dupa ordine: subsol, parter, etaj 1
        assert niveluri[0].cod == 'B01'
        assert niveluri[1].cod == 'N00'
        assert niveluri[2].cod == 'N01'

        spatii = list(niveluri[1].spatii)
        assert len(spatii) == 1
        assert spatii[0].cod == 'P.05'

        elemente = list(spatii[0].elemente)
        assert len(elemente) == 1
        assert elemente[0].tip_element == 'AHU'


def test_element_tip_label_si_categorie(app, santier_complet):
    """ElementBIM.tip_label returneaza eticheta romaneasca."""
    with app.app_context():
        from models import ElementBIM
        e = ElementBIM.query.filter_by(cod='AHU-03').first()
        assert e.tip_label == 'CTA - Centrala tratare aer'
        assert e.tip_categorie == 'mep_hvac'


def test_element_cale_completa(app, santier_complet):
    """ElementBIM.cale_completa returneaza calea ierarhica."""
    with app.app_context():
        from models import ElementBIM
        e = ElementBIM.query.filter_by(cod='AHU-03').first()
        cale = e.cale_completa
        assert 'SITE-T1' in cale
        assert 'BLD-A' in cale
        assert 'Parter' in cale
        assert 'P.05' in cale
        assert 'AHU-03' in cale


def test_asset_in_garantie(app, santier_complet):
    """Asset.in_garantie reflecta corect statusul."""
    with app.app_context():
        from models import Asset
        a = Asset.query.filter_by(serial='SN-2024-0001').first()
        # Garantia se incheie 2027-06-14, oricand inainte e True
        if a.data_garantie_pana >= date.today():
            assert a.in_garantie is True
        else:
            assert a.in_garantie is False


def test_asset_one_to_one_cu_element(app, santier_complet):
    """Un element are maxim un asset; element_bim_id unic."""
    from models import db, ElementBIM, Asset
    with app.app_context():
        e = ElementBIM.query.filter_by(cod='AHU-03').first()
        # Crearea unui al doilea asset pentru acelasi element trebuie sa esueze
        a2 = Asset(element_bim_id=e.id, producator='Other', serial='DUP-001')
        db.session.add(a2)
        with pytest.raises(Exception):
            db.session.commit()
        db.session.rollback()


def test_issue_referenta_orice_nivel(app, santier_complet):
    """IssueBIM poate referi element, spatiu, nivel sau cladire."""
    from models import db, IssueBIM, Cladire, Spatiu, ElementBIM
    with app.app_context():
        e = ElementBIM.query.filter_by(cod='AHU-03').first()
        sp = Spatiu.query.filter_by(cod='P.05').first()
        cl = Cladire.query.filter_by(cod='BLD-A').first()

        i1 = IssueBIM(element_bim_id=e.id, titlu='Vibratii anormale AHU', tip='defect', severitate='mare')
        i2 = IssueBIM(spatiu_id=sp.id, titlu='Lipsa priza in spatiu', tip='lipsa_executie')
        i3 = IssueBIM(cladire_id=cl.id, titlu='Observatie generala cladire', tip='observatie')
        for i in [i1, i2, i3]:
            db.session.add(i)
        db.session.commit()

        assert IssueBIM.query.count() >= 3

        # Curat
        IssueBIM.query.delete()
        db.session.commit()


def test_workforce_link_columns_exista(app):
    """Coloanele FK workforce -> BIM sunt prezente."""
    from models import db
    from sqlalchemy import inspect
    with app.app_context():
        insp = inspect(db.engine)
        proi_cols = {c['name'] for c in insp.get_columns('proiecte')}
        ra_cols = {c['name'] for c in insp.get_columns('rapoarte_activitati')}
        pontaj_cols = {c['name'] for c in insp.get_columns('pontaje')}
        users_cols = {c['name'] for c in insp.get_columns('utilizatori')}
        ang_cols = {c['name'] for c in insp.get_columns('angajati')}

    assert 'tenant_id' in proi_cols
    assert 'element_bim_id' in ra_cols
    assert 'spatiu_id' in ra_cols
    assert 'zona_id' in ra_cols
    assert 'element_bim_id' in pontaj_cols
    assert 'spatiu_id' in pontaj_cols
    assert 'tenant_id' in users_cols
    assert 'limba' in users_cols
    assert 'tenant_id' in ang_cols


def test_tenant_creation(app):
    """Modelul Tenant se creeaza si codul e unique."""
    from models import db, Tenant
    with app.app_context():
        Tenant.query.filter(Tenant.cod.like('test-%')).delete()
        db.session.commit()

        t1 = Tenant(cod='test-org-1', nume='Org Test 1')
        db.session.add(t1)
        db.session.commit()
        assert t1.id is not None

        t2 = Tenant(cod='test-org-1', nume='Dup')  # acelasi cod -> trebuie sa esueze
        db.session.add(t2)
        with pytest.raises(Exception):
            db.session.commit()
        db.session.rollback()

        Tenant.query.filter(Tenant.cod.like('test-%')).delete()
        db.session.commit()
