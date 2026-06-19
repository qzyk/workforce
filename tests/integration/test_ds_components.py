"""Teste DS faza 2 - biblioteca de componente Jinja (_components.html) + pagina demo /ghid/ds.

Verifica:
  - pagina demo randeaza 200 si contine clasele componentelor;
  - macro-urile nu arunca cu argumente minime;
  - _macros.html vechi (empty_state / next_hint) inca functioneaza si deleaga;
  - components.css e linkat in base.html si precache-uit in sw.js.
"""

from flask import render_template_string


def test_ghid_ds_randeaza_200(authenticated_client):
    """Bancul de componente /ghid/ds raspunde 200 si contine elementele cheie."""
    r = authenticated_client.get('/ghid/ds')
    assert r.status_code == 200
    html = r.data
    # cate o clasa reprezentativa pentru fiecare familie de componente
    for marker in (
        b'ed-hero', b'ed-page-header', b'ed-btn', b'ed-stat', b'ed-card',
        b'ed-badge', b'ed-table', b'ed-empty', b'ed-field', b'ed-filter-bar',
        b'ed-pagination', b'ed-stepper', b'ed-tabs', b'ed-hint',
    ):
        assert marker in html, f'lipseste {marker!r} din /ghid/ds'


def test_ghid_ds_confirm_form_foloseste_modal_global(authenticated_client):
    """confirm_form deleaga la modalul global (data-confirm-*), nu la confirm() nativ.

    Markup-ul NU mai foloseste un onclick inline (care se rupea cand mesajul avea
    ghilimele): url + mesaj vin prin atribute data-*, iar listener-ul delegat din
    main.js apeleaza confirmDelete.
    """
    r = authenticated_client.get('/ghid/ds')
    assert r.status_code == 200
    assert b'data-confirm-url=' in r.data
    assert b'data-confirm-mesaj=' in r.data
    # nu mai exista onclick inline cu confirmDelete (sursa bug-ului de quoting)
    assert b'onclick="confirmDelete(' not in r.data


def test_confirm_form_markup_valid_cu_mesaj_cu_ghilimele(app):
    """Mesaj cu apostrof + ghilimele: atributul data-* ramane intreg (HTML-escaped),
    iar dupa decodarea browserului redevine exact mesajul initial.

    Reproduce defectul vechi: {{ mesaj | tojson }} intr-un onclick="..." inchidea
    atributul prematur la prima ghilimea dubla. Acum nu mai e cazul.
    """
    import html as _html
    import re
    tpl = '{% import "_components.html" as ed %}{{ ed.confirm_form(url="/sterge/1", mesaj=m) }}'
    mesaj = 'Stergi "Hala" + L\'element?'
    with app.test_request_context():
        out = render_template_string(tpl, m=mesaj)
    # niciun onclick inline; doar atribute data-*
    assert 'onclick' not in out
    assert 'data-confirm-url="/sterge/1"' in out
    # atributul nu e rupt de ghilimele: o singura pereche data-confirm-mesaj="..."
    m = re.search(r'data-confirm-mesaj="([^"]*)"', out)
    assert m is not None, out
    # ghilimelele duble din mesaj sunt escapate ca entitate, nu lasate brute
    assert '"Hala"' not in m.group(1)
    # dupa decodarea HTML (ce vede browserul) redevine mesajul exact
    assert _html.unescape(m.group(1)) == mesaj


def test_confirm_form_default_foloseste_ghilimele_simple_in_apel(app):
    """confirm_form fara mesaj (cazul frecvent): butonul are mesajul implicit in
    data-confirm-mesaj, fara sa strice markup-ul. Verifica si butonul valid <button>."""
    tpl = '{% import "_components.html" as ed %}{{ ed.confirm_form(url="/x") }}'
    with app.test_request_context():
        out = render_template_string(tpl)
    assert 'data-confirm-url="/x"' in out
    assert 'Sunteti sigur' in out  # mesajul implicit ajunge in atribut
    assert '<button type="button"' in out


def test_macros_argumente_minime_nu_arunca(app):
    """Toate macro-urile randeaza fara eroare cu argumente minime."""
    tpl = """
    {% import "_components.html" as ed %}
    {{ ed.page_header() }}
    {{ ed.hero() }}
    {{ ed.btn() }}
    {{ ed.btn('X', submit=true) }}
    {{ ed.stat_card() }}
    {% call ed.card() %}corp{% endcall %}
    {{ ed.badge() }}
    {{ ed.badge('Activ', 'activ') }}
    {% call ed.data_table(['A','B']) %}<tr><td>1</td><td>2</td></tr>{% endcall %}
    {{ ed.empty_state() }}
    {{ ed.confirm_form() }}
    {{ ed.form_field('Nume') }}
    {% call ed.form_section('Sectiune') %}{{ ed.form_field('Camp') }}{% endcall %}
    {% call ed.filter_bar() %}{{ ed.form_field('q') }}{% endcall %}
    {{ ed.stepper(['a','b','c'], activ=1) }}
    {{ ed.tabs([{'label':'Unu','activ':true},{'label':'Doi','url':'/x'}]) }}
    {{ ed.next_hint('text') }}
    {{ ed.pagination(none, 'dashboard.ghid_ds') }}
    """
    with app.test_request_context():
        out = render_template_string(tpl)
    assert 'ed-hero' in out and 'ed-btn' in out and 'ed-stepper' in out


def test_macros_vechi_inca_functioneaza(app):
    """_macros.html (empty_state, next_hint) inca randeaza si deleaga la _components."""
    tpl = """
    {% import "_macros.html" as macros %}
    {{ macros.empty_state('inbox', 'Gol', 'Mesaj', cta_url='/x', cta_label='Adauga') }}
    {{ macros.next_hint('hint', url='/y', link_label='Mergi') }}
    """
    with app.test_request_context():
        out = render_template_string(tpl)
    # randarea vine prin clasele noi .ed-*
    assert 'ed-empty' in out and 'ed-hint' in out
    assert 'Gol' in out and 'hint' in out


def test_components_css_linkat_si_precache():
    """components.css e linkat in base.html si pre-cache-uit in sw.js (PWA offline)."""
    import os
    radacina = os.path.join(os.path.dirname(__file__), '..', '..')
    with open(os.path.join(radacina, 'templates', 'base.html'), encoding='utf-8') as f:
        base = f.read()
    assert 'css/components.css' in base
    with open(os.path.join(radacina, 'static', 'sw.js'), encoding='utf-8') as f:
        sw = f.read()
    assert '/static/css/components.css' in sw


def test_badge_mapare_centralizata_status(app):
    """Mapare status -> culoare: aprobat->success, expirat->danger, necunoscut->neutru."""
    tpl = """
    {% import "_components.html" as ed %}
    A:{{ ed.badge('A', 'aprobat') }}|E:{{ ed.badge('E', 'expirat') }}|N:{{ ed.badge('N', 'habarnu') }}
    """
    with app.test_request_context():
        out = render_template_string(tpl)
    assert 'ed-badge--success' in out
    assert 'ed-badge--danger' in out
    assert 'ed-badge--neutru' in out
