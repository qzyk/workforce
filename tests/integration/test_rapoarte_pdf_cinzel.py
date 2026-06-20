"""
Rapoarte Faza 2: branding Cinzel pe PDF de situatii lunare + procese verbale.

Verifica:
  - flag 'rapoarte-pdf-cinzel' exista in catalog si e default OFF
  - cu flag ON: PDF-ul (situatie + PV) foloseste fontul serif brandat
    (din rapoarte.brand.get_pdf_fonts) si CONTINE header-ul brandat
    (wordmark 'EDIFICO WORKFORCE SRL') - verificat in structura/textul PDF,
    nu doar ca nu crapa
  - cu flag OFF: comportament dinainte (Helvetica, fara wordmark, fara serif)
  - fallback fara fontul Cinzel (.ttf lipseste in repo) -> fara crash,
    cade pe Times (font serif standard reportlab)
  - regresie: exporturile inca se genereaza ca PDF valid (magic bytes %PDF)
  - helperul de logo (pdf_logo_flowable) e tolerant (None / Image, fara crash)

Toate PDF-urile sunt inspectate cu pypdf: BaseFonts embed-uite + text extras.
"""

from datetime import date
from decimal import Decimal

import pytest

pypdf = pytest.importorskip('pypdf')
pytest.importorskip('reportlab')


# ============================================================
# Helpers de inspectie PDF
# ============================================================

def _basefonts_din_pdf(path):
    """Multimea numelor /BaseFont embed-uite in PDF (ex. 'Helvetica-Bold')."""
    r = pypdf.PdfReader(path)
    fonts = set()
    for page in r.pages:
        res = page.get('/Resources')
        if not res or '/Font' not in res:
            continue
        for fobj in res['/Font'].values():
            fo = fobj.get_object()
            bf = fo.get('/BaseFont')
            if bf:
                # ReportLab prefixeaza subseturi cu 'ABCDEF+' - normalizam.
                nume = str(bf).lstrip('/')
                if '+' in nume:
                    nume = nume.split('+', 1)[1]
                fonts.add(nume)
    return fonts


def _text_din_pdf(path):
    r = pypdf.PdfReader(path)
    return '\n'.join(p.extract_text() for p in r.pages)


# ============================================================
# Fixtures de date (PV + situatie)
# ============================================================

@pytest.fixture
def pv_minim(app, admin_user):
    """Un ProcesVerbal minim cu participanti pentru export PDF."""
    from models import db, Proiect, Contract, ProcesVerbal
    with app.app_context():
        ProcesVerbal.query.filter_by(numar='CZ-PV').delete()
        Contract.query.filter_by(nr_contract='CZ-CTR').delete()
        Proiect.query.filter_by(cod_proiect='CZ-PRJ').delete()
        db.session.commit()

        p = Proiect(cod_proiect='CZ-PRJ', nume='Cinzel Test',
                    data_start=date(2026, 1, 1), status='activ')
        db.session.add(p); db.session.commit()
        c = Contract(proiect_id=p.id, nr_contract='CZ-CTR',
                     data_semnare=date(2026, 1, 15), status='activ',
                     beneficiar='Benef SRL', antreprenor='Antrep SA')
        db.session.add(c); db.session.commit()
        pv = ProcesVerbal(
            proiect_id=p.id, contract_id=c.id,
            tip='receptie_finala', numar='CZ-PV',
            data_emitere=date(2026, 2, 1),
            obiect='Receptia finala a lucrarilor',
            concluzii='Lucrarile au fost receptionate.',
        )
        pv.participanti = [
            {'nume': 'Ion Popescu', 'functie': 'Diriginte',
             'organizatie': 'Benef SRL'},
        ]
        db.session.add(pv); db.session.commit()
        yield pv.id


@pytest.fixture
def situatie_minim(app, admin_user):
    """O SituatieLunara minima cu o pozitie BoQ executata pentru export PDF."""
    from models import (
        db, Proiect, Contract, OfertaContract, PozitieBoQ,
        CantitateExecutataLunara, SituatieLunara,
    )
    with app.app_context():
        SituatieLunara.query.delete()
        CantitateExecutataLunara.query.delete()
        PozitieBoQ.query.filter(PozitieBoQ.cod_articol.like('CZ-%')).delete()
        OfertaContract.query.delete()
        Contract.query.filter_by(nr_contract='CZS-CTR').delete()
        Proiect.query.filter_by(cod_proiect='CZS-PRJ').delete()
        db.session.commit()

        p = Proiect(cod_proiect='CZS-PRJ', nume='Cinzel Sit',
                    data_start=date(2026, 1, 1), status='activ')
        db.session.add(p); db.session.commit()
        c = Contract(proiect_id=p.id, nr_contract='CZS-CTR',
                     data_semnare=date(2026, 1, 15), status='activ',
                     valoare_totala=Decimal('50000'), moneda='RON',
                     beneficiar='Benef SRL')
        db.session.add(c); db.session.commit()
        o = OfertaContract(contract_id=c.id, proiect_id=p.id, versiune=1,
                           data_emitere=date(2026, 1, 20),
                           valoare_totala=Decimal('50000'),
                           sursa_import='manual', aprobata=True)
        db.session.add(o); db.session.commit()
        pz = PozitieBoQ(oferta_id=o.id, proiect_id=p.id,
                        cod_articol='CZ-001', denumire='Beton armat',
                        um='mc', cantitate_oferta=Decimal('100'),
                        pret_unitar=Decimal('200'), categorie='mixt', ordine=1)
        db.session.add(pz); db.session.commit()
        ce = CantitateExecutataLunara(
            pozitie_boq_id=pz.id, proiect_id=p.id, an=2026, luna=3,
            cantitate_executata=Decimal('25'), valoare_calculata=Decimal('5000'),
            validat=True, validat_de_id=admin_user.id,
        )
        db.session.add(ce); db.session.commit()
        s = SituatieLunara(
            proiect_id=p.id, contract_id=c.id,
            an=2026, luna=3, status='emisa',
            valoare_totala_luna=Decimal('5000'),
            valoare_cumulat_la_zi=Decimal('5000'),
            procent_avans_total=Decimal('10'),
            numar_situatie='CZ-S-001',
        )
        db.session.add(s); db.session.commit()
        yield s.id


# ============================================================
# 1. Flag in catalog + default OFF
# ============================================================

def test_flag_rapoarte_pdf_cinzel_in_catalog():
    from services.feature_flags import KNOWN_FLAGS
    assert 'rapoarte-pdf-cinzel' in KNOWN_FLAGS
    desc = KNOWN_FLAGS['rapoarte-pdf-cinzel'].lower()
    assert 'cinzel' in desc and 'off' in desc


def test_flag_rapoarte_pdf_cinzel_default_off(app):
    from services.feature_flags import is_enabled
    with app.app_context():
        assert is_enabled('rapoarte-pdf-cinzel') is False


# ============================================================
# 2. Helper logo (tolerant)
# ============================================================

def test_pdf_logo_flowable_tolerant():
    """Returneaza un Image (daca exista PNG de brand) sau None, fara crash."""
    from rapoarte import brand
    logo = brand.pdf_logo_flowable()
    if logo is not None:
        from reportlab.platypus import Image
        assert isinstance(logo, Image)
        assert logo.drawHeight > 0 and logo.drawWidth > 0


def test_pdf_header_elements_cu_logo_nu_crapa():
    from rapoarte import brand
    els = brand.pdf_header_elements('TITLU', cu_logo=True)
    assert len(els) >= 2  # cel putin wordmark + spacer


# ============================================================
# 3. PV PDF: ON vs OFF
# ============================================================

class TestPVPdfBranding:
    def test_pv_off_comportament_dinainte(self, app, pv_minim):
        """Flag OFF: Helvetica-Bold pe titlu, fara wordmark, fara serif Times."""
        from services.pv_generator import genereaza_pv_pdf
        with app.app_context():
            path = genereaza_pv_pdf(pv_minim)

        fonts = _basefonts_din_pdf(path)
        text = _text_din_pdf(path)
        assert 'Helvetica-Bold' in fonts
        # serif brand NU e folosit cu OFF
        assert not any('Times' in f for f in fonts)
        # header brandat absent
        assert 'EDIFICO WORKFORCE SRL' not in text
        # continutul de baza ramane (regresie)
        assert 'RECEPTIE FINALA' in text

    def test_pv_on_foloseste_serif_brand_si_header(self, app, pv_minim):
        """
        Flag ON: header brandat (wordmark) prezent + fontul serif brandat e
        chiar folosit in PDF (verificare structurala: ON introduce un font
        serif absent in varianta OFF; functioneaza si pe Times-fallback si pe
        un Cinzel real, al carui /BaseFont intern difera de numele logic).
        """
        from services.feature_flags import set_flag
        from services.pv_generator import genereaza_pv_pdf
        from rapoarte import brand

        with app.app_context():
            # OFF mai intai (referinta), apoi ON.
            path_off = genereaza_pv_pdf(pv_minim)
            fonts_off = _basefonts_din_pdf(path_off)

            set_flag('rapoarte-pdf-cinzel', True, commit=True)
            serif, serif_bold = brand.get_pdf_fonts()
            path_on = genereaza_pv_pdf(pv_minim)

        fonts_on = _basefonts_din_pdf(path_on)
        text = _text_din_pdf(path_on)
        assert serif_bold  # get_pdf_fonts a returnat un nume de font valid

        # ON introduce cel putin un font nou (serif de titlu) fata de OFF ->
        # fontul brandat chiar e folosit in PDF (nu doar no-crash).
        assert fonts_on - fonts_off, (
            f'ON nu a adaugat niciun font nou: on={sorted(fonts_on)} '
            f'off={sorted(fonts_off)}'
        )
        # Header brandat prezent (verificare structurala a header-ului).
        assert 'EDIFICO WORKFORCE SRL' in text
        # Titlul de PV ramane.
        assert 'RECEPTIE FINALA' in text

    def test_pv_on_inca_pdf_valid(self, app, pv_minim):
        """Regresie: cu ON PDF-ul ramane valid (magic bytes %PDF)."""
        from services.feature_flags import set_flag
        from services.pv_generator import genereaza_pv_pdf
        with app.app_context():
            set_flag('rapoarte-pdf-cinzel', True, commit=True)
            path = genereaza_pv_pdf(pv_minim)
        with open(path, 'rb') as fh:
            assert fh.read(4) == b'%PDF'


# ============================================================
# 4. Situatie PDF: ON vs OFF
# ============================================================

class TestSituatiePdfBranding:
    def test_situatie_off_comportament_dinainte(self, app, situatie_minim):
        from services.situatii import export_situatie_pdf
        with app.app_context():
            path = export_situatie_pdf(situatie_minim)

        fonts = _basefonts_din_pdf(path)
        text = _text_din_pdf(path)
        assert 'Helvetica-Bold' in fonts
        assert not any('Times' in f for f in fonts)
        assert 'EDIFICO WORKFORCE SRL' not in text
        # continut de baza
        assert 'SITUATIE DE LUCRARI' in text

    def test_situatie_on_foloseste_serif_brand_si_header(self, app, situatie_minim):
        from services.feature_flags import set_flag
        from services.situatii import export_situatie_pdf
        from rapoarte import brand
        with app.app_context():
            path_off = export_situatie_pdf(situatie_minim)
            fonts_off = _basefonts_din_pdf(path_off)

            set_flag('rapoarte-pdf-cinzel', True, commit=True)
            serif, serif_bold = brand.get_pdf_fonts()
            path_on = export_situatie_pdf(situatie_minim)

        fonts_on = _basefonts_din_pdf(path_on)
        text = _text_din_pdf(path_on)
        assert serif_bold

        assert fonts_on - fonts_off, (
            f'ON nu a adaugat niciun font nou: on={sorted(fonts_on)} '
            f'off={sorted(fonts_off)}'
        )
        assert 'EDIFICO WORKFORCE SRL' in text
        assert 'SITUATIE DE LUCRARI' in text

    def test_situatie_on_inca_pdf_valid(self, app, situatie_minim):
        from services.feature_flags import set_flag
        from services.situatii import export_situatie_pdf
        with app.app_context():
            set_flag('rapoarte-pdf-cinzel', True, commit=True)
            path = export_situatie_pdf(situatie_minim)
        with open(path, 'rb') as fh:
            assert fh.read(4) == b'%PDF'


# ============================================================
# 5. Fallback fara font Cinzel - fara crash
# ============================================================

def test_fallback_fara_cinzel_nu_crapa(app, pv_minim):
    """
    Fara .ttf Cinzel in repo, get_pdf_fonts cade pe Times (serif standard).
    Cu flag ON, PDF-ul tot se genereaza valid, fara exceptie.
    """
    from services.feature_flags import set_flag
    from services.pv_generator import genereaza_pv_pdf
    from rapoarte import brand

    serif, serif_bold = brand.get_pdf_fonts()
    # In repo nu exista Cinzel -> fallback Times (documentat in brand.py).
    assert serif in ('EdificoSerif', 'Times-Roman')
    assert serif_bold in ('EdificoSerif', 'EdificoSerif-Bold', 'Times-Bold')

    with app.app_context():
        set_flag('rapoarte-pdf-cinzel', True, commit=True)
        path = genereaza_pv_pdf(pv_minim)
    with open(path, 'rb') as fh:
        assert fh.read(4) == b'%PDF'
