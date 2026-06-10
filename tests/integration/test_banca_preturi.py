"""Teste pentru banca de preturi de resurse (import + benchmark + idempotenta)."""

from decimal import Decimal

import pytest

from models import db, PretResursa
from services import banca_preturi as bp


CATALOG = {
    'C6_materiale': [
        {'cod': '2000030', 'denumire': 'Otel beton PC52', 'um': 'kg',
         'pret_unitar': 4.29, 'furnizor': 'Depozit'},
        {'cod': '11519465', 'denumire': 'Tub de protectie', 'um': 'm',
         'pret_unitar': 11.2, 'furnizor': 'Depozit'},
    ],
    'C7_manopera': [
        {'cod': '10200', 'meserie': 'Betonist', 'tarif_lei_ora': 29.0},
    ],
    'C8_utilaje': [
        {'cod': '1103', 'utilaj': 'Macara pe pneuri', 'tarif_unitar': 87.53},
    ],
    'C9_transport': [
        {'cod': 'TRA01A30', 'tip_transport': 'Transport rutier', 'tarif_unitar': 0.84},
    ],
    'F4_echipamente': [
        {'cod': 'AM300', 'denumire': 'Unitate exterioara VRF', 'um': 'buc',
         'pret_unitar': 340400.0},
    ],
}


@pytest.fixture(autouse=True)
def _curata_pret(app):
    """Sterge banca de preturi inainte de fiecare test (nu e in cleanup-ul global)."""
    with app.app_context():
        PretResursa.query.delete()
        db.session.commit()
    yield


def test_import_catalog_creeaza_toate_tipurile(app):
    with app.app_context():
        stats = bp.importa_din_catalog(CATALOG, sursa='Test Obiectiv')
        assert stats['creat'] == 6           # 2 + 1 + 1 + 1 + 1
        assert PretResursa.query.count() == 6
        # tipuri corecte
        tipuri = {p.tip for p in PretResursa.query.all()}
        assert tipuri == {'material', 'manopera', 'utilaj', 'transport', 'echipament'}
        # UM default pentru manopera/transport
        man = PretResursa.query.filter_by(tip='manopera').first()
        assert man.um == 'ora'
        tr = PretResursa.query.filter_by(tip='transport').first()
        assert tr.um == 'to*km'
        # furnizor pastrat doar la material
        mat = PretResursa.query.filter_by(cod='2000030').first()
        assert mat.furnizor == 'Depozit'
        assert mat.pret_unitar == Decimal('4.29')


def test_idempotenta_reimport_aceeasi_sursa(app):
    with app.app_context():
        bp.importa_din_catalog(CATALOG, sursa='Sursa A')
        n1 = PretResursa.query.count()
        # re-import aceeasi sursa cu pret modificat -> update, nu duplicat
        cat2 = {'C6_materiale': [{'cod': '2000030', 'denumire': 'Otel beton PC52',
                                  'um': 'kg', 'pret_unitar': 5.00, 'furnizor': 'Depozit'}]}
        stats = bp.importa_din_catalog(cat2, sursa='Sursa A')
        assert stats['actualizat'] == 1
        assert stats['creat'] == 0
        assert PretResursa.query.count() == n1   # fara duplicat
        assert PretResursa.query.filter_by(cod='2000030').first().pret_unitar == Decimal('5.00')


def test_pret_referinta_mediana_intre_surse(app):
    with app.app_context():
        # acelasi cod, 2 surse diferite -> mediana
        bp.importa_din_catalog(
            {'C6_materiale': [{'cod': 'X1', 'denumire': 'Mat', 'um': 'kg', 'pret_unitar': 4.0}]},
            sursa='Proiect 1')
        bp.importa_din_catalog(
            {'C6_materiale': [{'cod': 'X1', 'denumire': 'Mat', 'um': 'kg', 'pret_unitar': 6.0}]},
            sursa='Proiect 2')
        assert PretResursa.query.filter_by(cod='X1').count() == 2
        assert bp.pret_referinta('X1') == Decimal('5.0')
        assert bp.pret_referinta('inexistent') is None


def test_rezumat_si_cauta(app):
    with app.app_context():
        bp.importa_din_catalog(CATALOG, sursa='Test')
        rez = bp.rezumat()
        assert rez['material']['n_coduri'] == 2
        assert rez['manopera']['n'] == 1
        # cautare pe denumire
        r = bp.cauta(q='betonist')
        assert len(r) == 1 and r[0].tip == 'manopera'
        # filtru pe tip
        assert all(p.tip == 'material' for p in bp.cauta(tip='material'))
