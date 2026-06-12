"""
Teste unit pentru Design System faza 1 (tokens.css + integrare).

Verifica fara aplicatie Flask (doar continut de fisiere):
  - tokens.css exista si defineste variabilele de baza
  - base.html include tokens.css INAINTE de style.css
  - service worker-ul precache-uieste tokens.css si are versiunea incrementata
  - variabilele vechi din style.css NU au fost sterse (strict aditiv)
"""
from pathlib import Path

RADACINA = Path(__file__).resolve().parents[2]
TOKENS = RADACINA / 'static' / 'css' / 'tokens.css'
STYLE = RADACINA / 'static' / 'css' / 'style.css'
BASE_HTML = RADACINA / 'templates' / 'base.html'
SW = RADACINA / 'static' / 'sw.js'


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
