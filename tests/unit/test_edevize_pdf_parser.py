"""
Teste unit pentru EDevizePDFParser (Faza 11.5).

Foloseste un PDF eDevize sintetic construit cu reportlab (vezi
tests/fixtures/imports/build_sample_edevize_pdf.py). Replica structura
formularului F3 real (testat pe DEVIZ SAPUNARI.pdf - 111 pagini).

Plus un test opt-in cu PDF real SAPUNARI (skip daca nu e in Downloads).
"""

import os
from decimal import Decimal
from pathlib import Path

import pytest

from services.parsers.edevize_pdf_parser import EDevizePDFParser
from services.parsers.base import ParseError
from tests.fixtures.imports.build_sample_edevize_pdf import build_sample_pdf


REAL_SAPUNARI_PATH = os.path.expanduser('~/Downloads/DEVIZ SAPUNARI.pdf')


@pytest.fixture
def sample_pdf(tmp_path):
    """Construieste un PDF eDevize sintetic in tmp_path."""
    return build_sample_pdf(str(tmp_path / 'sample_edevize.pdf'))


# ============================================================
# Synthetic PDF (CI-friendly)
# ============================================================

class TestEDevizePDFParserSynthetic:
    def test_parses_without_errors(self, sample_pdf):
        r = EDevizePDFParser().parse(sample_pdf)
        assert not r.has_errors, f'Errors: {r.errors}'
        assert r.sursa == 'edevize_pdf'

    def test_skips_centralizator_page(self, sample_pdf):
        r = EDevizePDFParser().parse(sample_pdf)
        # 3 pagini total: pagina 1 centralizator (skip), pagina 2-3 F3 (parse)
        assert r.stats['total_pages'] == 3
        assert r.stats['f3_pages'] == 2

    def test_extracts_5_articles_total(self, sample_pdf):
        r = EDevizePDFParser().parse(sample_pdf)
        # Fixture: 3 articole pe pagina 2 + 2 articole pe pagina 3
        assert len(r.entities) == 5

    def test_cod_articol_preserves_suffixes(self, sample_pdf):
        r = EDevizePDFParser().parse(sample_pdf)
        codes = [e['cod_articol'] for e in r.entities]
        # Sufixele speciale eDevize trebuie pastrate intacte
        assert 'CR06A%' in codes
        assert 'CK03B02^' in codes
        assert 'RMA02A#' in codes

    def test_cod_capitol_from_stadiul_fizic(self, sample_pdf):
        r = EDevizePDFParser().parse(sample_pdf)
        # Pagina 2 are "Stadiul fizic: 1 REZISTENTA"
        # Pagina 3 are "Stadiul fizic: 2 ARHITECTURA"
        by_code = {e['cod_articol']: e for e in r.entities}
        assert by_code['SLVI03B5']['cod_capitol'] == '1 REZISTENTA'
        assert by_code['RMA02A#']['cod_capitol'] == '2 ARHITECTURA'

    def test_multiline_denumire_concatenated(self, sample_pdf):
        r = EDevizePDFParser().parse(sample_pdf)
        # CK03B02^ are denumire pe 2 randuri in PDF, trebuie concatenata
        by_code = {e['cod_articol']: e for e in r.entities}
        denumire = by_code['CK03B02^']['denumire']
        # Ambele parti trebuie sa apara
        assert 'Plafon casetat' in denumire
        assert 'structura de sustinere' in denumire

    def test_oneliner_denumire_short(self, sample_pdf):
        r = EDevizePDFParser().parse(sample_pdf)
        by_code = {e['cod_articol']: e for e in r.entities}
        # SLVI03B5 - "Sapatura" e one-liner cu denumire scurta
        assert by_code['SLVI03B5']['denumire'] == 'Sapatura'

    def test_decimal_thousands_separator_parsed(self, sample_pdf):
        """eDevize PDF: 'cant=2,260.000' (US-style) -> Decimal('2260.000')."""
        r = EDevizePDFParser().parse(sample_pdf)
        by_code = {e['cod_articol']: e for e in r.entities}
        # SLVI03B5: cant=2,260.000
        assert by_code['SLVI03B5']['cantitate_oferta'] == Decimal('2260.000')
        # CK03B02^: cant=1,537.000
        assert by_code['CK03B02^']['cantitate_oferta'] == Decimal('1537.000')

    def test_value_subroutes_extracted(self, sample_pdf):
        r = EDevizePDFParser().parse(sample_pdf)
        by_code = {e['cod_articol']: e for e in r.entities}
        # CR06A%: material=19.27, manopera=20.70, utilaj=0, transport=0
        cr = by_code['CR06A%']
        assert cr['valoare_materiale_unitar'] == Decimal('19.27')
        assert cr['valoare_manopera_unitar'] == Decimal('20.70')
        assert cr['valoare_utilaj_unitar'] == Decimal('0.00')
        assert cr['valoare_transport_unitar'] == Decimal('0.00')

    def test_categorie_inferred_correctly(self, sample_pdf):
        r = EDevizePDFParser().parse(sample_pdf)
        by_code = {e['cod_articol']: e for e in r.entities}
        # SLVI03B5: doar utilaj nonzero -> categorie = 'utilaje'
        assert by_code['SLVI03B5']['categorie'] == 'utilaje'
        # CR06A%: material + manopera nonzero -> 'mixt'
        assert by_code['CR06A%']['categorie'] == 'mixt'

    def test_ordine_assigned_globally(self, sample_pdf):
        r = EDevizePDFParser().parse(sample_pdf)
        ordini = [e['ordine'] for e in r.entities]
        # Ordinea trebuie sa fie globala (1..5), nu per-deviz
        assert ordini == [1, 2, 3, 4, 5]

    def test_stats_populated(self, sample_pdf):
        r = EDevizePDFParser().parse(sample_pdf)
        assert r.stats['entities_count'] == 5
        assert r.stats['warnings_count'] == 0
        assert r.stats['extracted_chars'] > 0


# ============================================================
# Error cases
# ============================================================

class TestEDevizePDFParserErrors:
    def test_invalid_pdf_raises_parse_error(self, tmp_path):
        bad = tmp_path / 'bad.pdf'
        bad.write_bytes(b'not a real pdf')
        with pytest.raises(ParseError):
            EDevizePDFParser().parse(str(bad))

    def test_no_f3_pages_returns_error(self, tmp_path):
        """PDF valid dar fara pagini F3 (ex: doar centralizator)."""
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4

        path = tmp_path / 'no_f3.pdf'
        c = canvas.Canvas(str(path), pagesize=A4)
        c.drawString(100, 700, 'CENTRALIZATORUL pe obiectiv')
        c.drawString(100, 680, 'TOTAL: 100,000')
        c.showPage()
        c.save()

        r = EDevizePDFParser().parse(str(path))
        assert r.has_errors
        assert 'F3' in r.errors[0]


# ============================================================
# Optional test cu PDF real SAPUNARI (skip daca nu e in Downloads)
# ============================================================

@pytest.mark.skipif(
    not os.path.exists(REAL_SAPUNARI_PATH),
    reason=f'PDF real SAPUNARI nu e in {REAL_SAPUNARI_PATH} - test optional'
)
class TestEDevizePDFParserReal:
    """Test cu PDF real generat de eDevize.ro - confirma parser-ul pe layout real."""

    def test_parses_sapunari_without_errors(self):
        r = EDevizePDFParser().parse(REAL_SAPUNARI_PATH)
        assert not r.has_errors, f'Errors: {r.errors}'

    def test_extracts_many_articles(self):
        r = EDevizePDFParser().parse(REAL_SAPUNARI_PATH)
        # SAPUNARI are ~490 articole. Verific ca am >= 400 (toleranta layout)
        assert len(r.entities) >= 400, f'Doar {len(r.entities)} articole - layout schimbat?'

    def test_capitole_variate_detected(self):
        r = EDevizePDFParser().parse(REAL_SAPUNARI_PATH)
        capitole = {e['cod_capitol'] for e in r.entities if e['cod_capitol']}
        # SAPUNARI are minim: REZISTENTA, ARHITECTURA, ELECTRICE, SANITARE,
        # TERMICE, VENTILATII, MONTAJ
        assert len(capitole) >= 5

    def test_codes_with_special_suffixes(self):
        """SAPUNARI contine articole cu sufixe %, #, ^, * - trebuie pastrate."""
        r = EDevizePDFParser().parse(REAL_SAPUNARI_PATH)
        suffix_chars = set('%#^*>')
        with_suffix = [e for e in r.entities
                       if e['cod_articol'] and e['cod_articol'][-1] in suffix_chars]
        assert len(with_suffix) > 10, 'Articolele cu sufixe speciale lipsesc - parser bug.'
