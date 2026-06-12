"""
Teste unit pentru Design System faza 1 (tokens.css + integrare).

Verifica fara aplicatie Flask (doar continut de fisiere):
  - tokens.css exista si defineste variabilele de baza
  - base.html include tokens.css INAINTE de style.css
  - service worker-ul precache-uieste tokens.css si are versiunea incrementata
  - variabilele vechi din style.css NU au fost sterse (strict aditiv)
  - constantele de contrast trec efectiv pragul WCAG AA (calcul real, nu comentariu)
"""
import re
from pathlib import Path

RADACINA = Path(__file__).resolve().parents[2]
TOKENS = RADACINA / 'static' / 'css' / 'tokens.css'
STYLE = RADACINA / 'static' / 'css' / 'style.css'
BASE_HTML = RADACINA / 'templates' / 'base.html'
SW = RADACINA / 'static' / 'sw.js'


def _luminanta(hexc):
    """Luminanta relativa WCAG pentru o culoare hex (#RRGGBB)."""
    hexc = hexc.lstrip('#')
    componente = [int(hexc[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in componente]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(culoare, fundal):
    """Raport de contrast WCAG intre doua culori hex."""
    l1, l2 = _luminanta(culoare), _luminanta(fundal)
    lmax, lmin = max(l1, l2), min(l1, l2)
    return (lmax + 0.05) / (lmin + 0.05)


def _valoare_token(nume):
    """Extrage valoarea hex a unei variabile --ed-* din tokens.css."""
    continut = TOKENS.read_text(encoding='utf-8')
    m = re.search(rf'{re.escape(nume)}:\s*(#[0-9A-Fa-f]{{6}})', continut)
    assert m, f'nu gasesc valoare hex pentru {nume} in tokens.css'
    return m.group(1)


def test_tokens_css_exista_si_are_variabile():
    continut = TOKENS.read_text(encoding='utf-8')
    for variabila in (
        '--ed-color-gold:',
        '--ed-color-gold-ink:',
        '--ed-color-navy:',
        '--ed-color-warning:',
        '--ed-color-warning-bg:',
        '--ed-color-text-faint:',
        '--ed-focus-ring:',
        '--ed-radius:',
    ):
        assert variabila in continut, f'lipseste {variabila} din tokens.css'


def test_tokens_css_are_focus_visible_si_reduced_motion():
    continut = TOKENS.read_text(encoding='utf-8')
    assert ':focus-visible' in continut
    assert 'prefers-reduced-motion' in continut


def test_base_html_include_tokens_inainte_de_style():
    continut = BASE_HTML.read_text(encoding='utf-8')
    poz_tokens = continut.find("css/tokens.css")
    poz_style = continut.find("css/style.css")
    assert poz_tokens != -1, 'base.html nu include tokens.css'
    assert poz_style != -1, 'base.html nu include style.css'
    assert poz_tokens < poz_style, 'tokens.css trebuie inclus INAINTE de style.css'


def test_sw_precache_tokens_si_versiune_noua():
    continut = SW.read_text(encoding='utf-8')
    assert '/static/css/tokens.css' in continut, 'tokens.css lipseste din PRECACHE_URLS'
    assert "'edifico-v1'" not in continut, 'versiunea cache trebuie incrementata (era edifico-v1)'


def test_style_css_pastreaza_variabilele_vechi():
    # strict aditiv: variabilele istorice raman definite si nedenumite
    continut = STYLE.read_text(encoding='utf-8')
    for variabila in (
        '--primary:',
        '--secondary:',
        '--gray-400:',
        '--gray-500:',
        '--edifico-gold:',
    ):
        assert variabila in continut, f'variabila veche {variabila} a disparut din style.css'


# ===== Invarianti de contrast WCAG (remedieri review) =====
# Fundalurile reale din aplicatie pe care sta textul "faint":
#   alb (header, carduri, dropdown), --bg #f0f2f5 (body / .main-footer),
#   --gray-50 #fafafa (fundalul inputurilor, deci ::placeholder)
FUNDALURI_TEXT_FAINT = ('#FFFFFF', '#f0f2f5', '#fafafa')


def test_text_faint_trece_aa_pe_toate_fundalurile():
    culoare = _valoare_token('--ed-color-text-faint')
    for fundal in FUNDALURI_TEXT_FAINT:
        raport = _contrast(culoare, fundal)
        assert raport >= 4.5, (
            f'text-faint {culoare} pe {fundal} = {raport:.2f}:1, sub pragul AA 4.5:1'
        )


def test_text_faint_din_style_css_e_sincronizat_cu_tokenul():
    # cele 13 corectii hardcodate din style.css trebuie sa foloseasca aceeasi nuanta
    culoare = _valoare_token('--ed-color-text-faint')
    continut = STYLE.read_text(encoding='utf-8')
    assert culoare.upper().lstrip('#') in continut.upper(), (
        f'style.css nu foloseste nuanta text-faint {culoare} din tokens.css'
    )
    assert '6F7886' not in continut.upper(), (
        'style.css mai contine vechiul #6F7886 (4.46:1 pe alb — sub AA)'
    )


def test_gold_ink_trece_aa_pe_cream_si_alb():
    culoare = _valoare_token('--ed-color-gold-ink')
    cream = _valoare_token('--ed-color-cream')
    for fundal in ('#FFFFFF', cream):
        raport = _contrast(culoare, fundal)
        assert raport >= 4.5, (
            f'gold-ink {culoare} pe {fundal} = {raport:.2f}:1, sub pragul AA 4.5:1'
        )


def test_badge_warning_trece_aa():
    text = _valoare_token('--ed-color-warning')
    fundal = _valoare_token('--ed-color-warning-bg')
    assert _contrast(text, fundal) >= 4.5


def test_focus_ring_solid_si_outline_nu_e_none():
    continut = TOKENS.read_text(encoding='utf-8')
    # inelul foloseste cerneala solida (gold-ink), nu gold semi-transparent (~1.4:1)
    assert 'var(--ed-color-gold-ink)' in re.search(
        r'--ed-focus-ring:([^;]+);', continut).group(1), (
        'focus ring trebuie sa foloseasca gold-ink solid (WCAG 1.4.11 cere >=3:1)'
    )
    # gold-ink ca inel de focus: >=3:1 (non-text) pe alb si pe fundalul body
    ink = _valoare_token('--ed-color-gold-ink')
    for fundal in ('#FFFFFF', '#f0f2f5'):
        assert _contrast(ink, fundal) >= 3.0
    # outline transparent (NU none) — pastreaza indicatorul in forced-colors mode
    regula_focus = continut[continut.find(':focus-visible'):]
    assert 'outline: none' not in regula_focus, (
        'outline: none ascunde focusul in forced-colors mode — foloseste transparent'
    )
    assert 'outline: 2px solid transparent' in regula_focus
