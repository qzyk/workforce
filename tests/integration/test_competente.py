"""Teste pentru modulul Competente (Workforce Faza 3).

Acopera:
- serviciul de matching (tokenizare, scor pe nivel, expirare, lista pe categorie)
- CRUD nomenclator competenta prin UI (creare / editare / dezactivare)
- atribuire competenta pe angajat (+ update pe index unic)
- matching de angajati pe CategorieActivitate (potrivire pe continut)
- migrarea idempotenta specializari -> competente (nedistructiva)
- regresie flag OFF (toate rutele 404)
"""

from datetime import date, timedelta

import pytest

from models import (
    db, Angajat, Competenta, AngajatCompetenta, CategorieActivitate,
)
from services import competente as competente_srv
from services.feature_flags import set_flag


# ------------------------------------------------------------------ fixtures

@pytest.fixture(autouse=True)
def _curata_competente(app):
    """Curata tabelele de competente intre teste (nu sunt in cleanup-ul global)."""
    yield
    with app.app_context():
        AngajatCompetenta.query.delete()
        Competenta.query.delete()
        CategorieActivitate.query.filter(
            CategorieActivitate.denumire.like('CompTest%')
        ).delete(synchronize_session=False)
        Angajat.query.filter(Angajat.cnp.like('19606060%')).delete(
            synchronize_session=False)
        db.session.commit()


@pytest.fixture
def _angajat(app):
    with app.app_context():
        a = Angajat(cnp='1960606060601', nume='CompTest', prenume='Vasile',
                    functie='Sudor', tip_contract='nedeterminat',
                    salariu_baza=5000, data_angajare=date(2024, 1, 1),
                    status='activ')
        db.session.add(a)
        db.session.commit()
        return a.id


@pytest.fixture
def _flag_on(app):
    with app.app_context():
        set_flag('competente', True)
    yield
    with app.app_context():
        set_flag('competente', False)


# ------------------------------------------------------------------ serviciu matching

def test_tokenizare_fara_diacritice_si_stopwords(app):
    with app.app_context():
        toks = competente_srv.tokenizeaza('Lucrari de Sudura Inox')
        # 'lucrari' si 'de' sunt stopwords / prea scurte; diacriticele dispar
        assert 'sudura' in toks
        assert 'inox' in toks
        assert 'lucrari' not in toks
        assert 'de' not in toks


def test_scor_potrivire_pe_nivel(app, _angajat):
    with app.app_context():
        c = Competenta(nume='Sudura TIG', categorie='sudura', activ=True)
        db.session.add(c)
        db.session.flush()
        db.session.add(AngajatCompetenta(angajat_id=_angajat,
                                         competenta_id=c.id, nivel=4))
        cat = CategorieActivitate(denumire='CompTest Lucrari de sudura conducte',
                                  activa=True)
        db.session.add(cat)
        db.session.commit()

        info = competente_srv.scor_potrivire_angajat(_angajat, cat)
        assert info['scor'] == 4  # nivelul competentei potrivite
        assert len(info['competente']) == 1
        assert info['expirate'] == []


def test_scor_zero_categorie_nerelevanta(app, _angajat):
    with app.app_context():
        c = Competenta(nume='Electrician', categorie='electric', activ=True)
        db.session.add(c)
        db.session.flush()
        db.session.add(AngajatCompetenta(angajat_id=_angajat,
                                         competenta_id=c.id, nivel=5))
        cat = CategorieActivitate(denumire='CompTest Sapaturi manuale', activa=True)
        db.session.add(cat)
        db.session.commit()

        info = competente_srv.scor_potrivire_angajat(_angajat, cat)
        assert info['scor'] == 0
        assert info['competente'] == []


def test_competenta_expirata_nu_intra_in_scor(app, _angajat):
    with app.app_context():
        c = Competenta(nume='Sudura conducte', categorie='sudura', activ=True)
        db.session.add(c)
        db.session.flush()
        # Expirata anul trecut
        db.session.add(AngajatCompetenta(
            angajat_id=_angajat, competenta_id=c.id, nivel=5,
            data_expirare=date.today() - timedelta(days=10)))
        cat = CategorieActivitate(denumire='CompTest Lucrari de sudura', activa=True)
        db.session.add(cat)
        db.session.commit()

        info = competente_srv.scor_potrivire_angajat(_angajat, cat)
        assert info['scor'] == 0
        # Dar e semnalata ca expirata (potrivita pe continut, doar invalida)
        assert len(info['expirate']) == 1
        assert info['expirate'][0].competenta.nume == 'Sudura conducte'


def test_competenta_inactiva_ignorata(app, _angajat):
    with app.app_context():
        c = Competenta(nume='Sudura MIG', categorie='sudura', activ=False)
        db.session.add(c)
        db.session.flush()
        db.session.add(AngajatCompetenta(angajat_id=_angajat,
                                         competenta_id=c.id, nivel=5))
        cat = CategorieActivitate(denumire='CompTest Lucrari de sudura', activa=True)
        db.session.add(cat)
        db.session.commit()

        info = competente_srv.scor_potrivire_angajat(_angajat, cat)
        assert info['scor'] == 0  # competenta inactiva nu conteaza


def test_angajati_pentru_categorie_ordonat(app, _angajat):
    with app.app_context():
        # Al doilea angajat cu nivel mai mic pe aceeasi competenta
        a2 = Angajat(cnp='1960606060602', nume='CompTest', prenume='Gheorghe',
                     functie='Sudor', data_angajare=date(2024, 1, 1), status='activ')
        db.session.add(a2)
        db.session.flush()
        c = Competenta(nume='Sudura speciala', categorie='sudura', activ=True)
        db.session.add(c)
        db.session.flush()
        db.session.add(AngajatCompetenta(angajat_id=_angajat, competenta_id=c.id, nivel=5))
        db.session.add(AngajatCompetenta(angajat_id=a2.id, competenta_id=c.id, nivel=2))
        cat = CategorieActivitate(denumire='CompTest Lucrari de sudura', activa=True)
        db.session.add(cat)
        db.session.commit()

        rez = competente_srv.angajati_pentru_categorie(cat)
        scoruri = [r['scor'] for r in rez]
        assert scoruri == sorted(scoruri, reverse=True)
        assert rez[0]['scor'] == 5  # nivelul cel mai mare primul


# ------------------------------------------------------------------ CRUD nomenclator UI

def test_creare_competenta_ui(app, authenticated_client, _flag_on):
    resp = authenticated_client.post('/competente/nou', data={
        'nume': 'Montaj structuri metalice',
        'categorie': 'structuri',
        'descriere': 'Asamblare structuri din otel',
        'necesita_certificare': 'y',
        'valabilitate_luni': '24',
        'activ': 'y',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        c = Competenta.query.filter_by(nume='Montaj structuri metalice').first()
        assert c is not None
        assert c.categorie == 'structuri'
        assert c.necesita_certificare is True
        assert c.valabilitate_luni == 24


def test_editare_competenta_ui(app, authenticated_client, _flag_on):
    with app.app_context():
        c = Competenta(nume='Vopsitorie', categorie='finisaje', activ=True)
        db.session.add(c)
        db.session.commit()
        cid = c.id
    resp = authenticated_client.post(f'/competente/{cid}/editeaza', data={
        'nume': 'Vopsitorie industriala',
        'categorie': 'finisaje',
        'activ': 'y',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert Competenta.query.get(cid).nume == 'Vopsitorie industriala'


def test_dezactivare_competenta_soft(app, authenticated_client, _flag_on):
    with app.app_context():
        c = Competenta(nume='Dulgherie', categorie='lemn', activ=True)
        db.session.add(c)
        db.session.commit()
        cid = c.id
    resp = authenticated_client.post(f'/competente/{cid}/sterge', follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        c = Competenta.query.get(cid)
        assert c is not None  # nu se sterge fizic
        assert c.activ is False


def test_operator_nu_poate_crea_competenta(app, operator_client, _flag_on):
    resp = operator_client.post('/competente/nou', data={
        'nume': 'Interzis', 'activ': 'y',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert Competenta.query.filter_by(nume='Interzis').first() is None


# ------------------------------------------------------------------ atribuire pe angajat

def test_atribuire_competenta_ui(app, authenticated_client, _flag_on, _angajat):
    with app.app_context():
        c = Competenta(nume='Macaragiu', categorie='utilaje', activ=True)
        db.session.add(c)
        db.session.commit()
        cid = c.id
    resp = authenticated_client.post(f'/competente/angajat/{_angajat}/adauga', data={
        'competenta_id': cid,
        'nivel': '4',
        'data_obtinere': '2025-01-15',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        ac = AngajatCompetenta.query.filter_by(angajat_id=_angajat,
                                               competenta_id=cid).first()
        assert ac is not None
        assert ac.nivel == 4


def test_atribuire_dubla_actualizeaza(app, authenticated_client, _flag_on, _angajat):
    """A doua atribuire a aceleiasi competente o actualizeaza (index unic)."""
    with app.app_context():
        c = Competenta(nume='ISCIR', categorie='autorizatii', activ=True)
        db.session.add(c)
        db.session.commit()
        cid = c.id
    authenticated_client.post(f'/competente/angajat/{_angajat}/adauga', data={
        'competenta_id': cid, 'nivel': '2',
    }, follow_redirects=True)
    authenticated_client.post(f'/competente/angajat/{_angajat}/adauga', data={
        'competenta_id': cid, 'nivel': '5',
    }, follow_redirects=True)
    with app.app_context():
        atribuiri = AngajatCompetenta.query.filter_by(
            angajat_id=_angajat, competenta_id=cid).all()
        assert len(atribuiri) == 1  # nu s-a dublat
        assert atribuiri[0].nivel == 5  # s-a actualizat


def test_stergere_atribuire(app, authenticated_client, _flag_on, _angajat):
    with app.app_context():
        c = Competenta(nume='Schele', categorie='montaj', activ=True)
        db.session.add(c)
        db.session.flush()
        ac = AngajatCompetenta(angajat_id=_angajat, competenta_id=c.id, nivel=3)
        db.session.add(ac)
        db.session.commit()
        acid = ac.id
    resp = authenticated_client.post(f'/competente/atribuire/{acid}/sterge',
                                     follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert AngajatCompetenta.query.get(acid) is None


# ------------------------------------------------------------------ matching UI

def test_matching_ui_pe_categorie(app, authenticated_client, _flag_on, _angajat):
    with app.app_context():
        c = Competenta(nume='Sudura conducte', categorie='sudura', activ=True)
        db.session.add(c)
        db.session.flush()
        db.session.add(AngajatCompetenta(angajat_id=_angajat,
                                         competenta_id=c.id, nivel=4))
        cat = CategorieActivitate(denumire='CompTest Lucrari de sudura conducte',
                                  activa=True)
        db.session.add(cat)
        db.session.commit()
        catid = cat.id
    resp = authenticated_client.get(
        f'/competente/matching?categorie_activitate_id={catid}')
    assert resp.status_code == 200
    assert b'CompTest' in resp.data
    assert b'Vasile' in resp.data  # angajatul potrivit apare


# ------------------------------------------------------------------ migrare specializari

def test_migrare_specializari_idempotenta(app):
    from scripts.migrare_specializari_competente import migreaza
    with app.app_context():
        a = Angajat(cnp='1960606060603', nume='CompTest', prenume='Migrat',
                    functie='Muncitor', data_angajare=date(2024, 1, 1),
                    status='activ', specializari='Sudura, Macara, sudura')
        db.session.add(a)
        db.session.commit()

    r1 = migreaza(app)
    r2 = migreaza(app)  # a doua rulare nu mai creeaza nimic
    assert r1['competente_create'] == 2  # 'Sudura' si 'Macara' (dedup case-insensitive)
    assert r1['atribuiri_create'] == 2
    assert r2['competente_create'] == 0
    assert r2['atribuiri_create'] == 0

    with app.app_context():
        a = Angajat.query.filter_by(cnp='1960606060603').first()
        # textul ramane neschimbat (nedistructiv)
        assert a.specializari == 'Sudura, Macara, sudura'


# ------------------------------------------------------------------ flag OFF

def test_flag_off_lista_404(app, authenticated_client):
    with app.app_context():
        set_flag('competente', False)
    assert authenticated_client.get('/competente/').status_code == 404


def test_flag_off_matching_404(app, authenticated_client):
    with app.app_context():
        set_flag('competente', False)
    assert authenticated_client.get('/competente/matching').status_code == 404


def test_flag_off_atribuie_404(app, authenticated_client, _angajat):
    with app.app_context():
        set_flag('competente', False)
    assert authenticated_client.get(
        f'/competente/angajat/{_angajat}/adauga').status_code == 404


def test_flag_off_fisa_fara_tab_competente(app, authenticated_client, _angajat):
    """Cu flag OFF, fisa angajatului nu contine tab-ul de competente."""
    with app.app_context():
        set_flag('competente', False)
    resp = authenticated_client.get(f'/angajati/{_angajat}')
    assert resp.status_code == 200
    assert b'data-tab="competente"' not in resp.data
