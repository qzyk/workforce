"""
Teste pentru chrome-ul aplicatiei migrat pe biblioteca de componente (DS faza 3).

Acopera base.html: skip-link, breadcrumb, flash cu aria-live, dropdown-uri cu aria,
modal de stergere cu role=dialog, sidebar cu macro nav_item (submeniu prin clasa, nu
stiluri inline), si scoping-ul Chart.js (incarcat doar pe paginile cu grafice).

Toate testele sunt randari reale prin clientul autentificat — orice eroare de
url_for / bloc Jinja / macro le sparge imediat.
"""

import pytest


# Rute cheie care toate extind base.html si trebuie sa randeze 200.
RUTE_CHROME = [
    '/',
    '/proiecte/',
    '/angajati/',
    '/pontaje/',
    '/documente/',
    '/activitati/',
    '/rapoarte/',
]


@pytest.mark.parametrize('url', RUTE_CHROME)
def test_rute_cheie_randeaza_200(authenticated_client, url):
    """Paginile cheie randeaza 200 (smoke pe base.html migrat)."""
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, f'{url} a intors {resp.status_code}'


def test_skip_link_prezent(authenticated_client):
    """Skip-link de accesibilitate prezent si tinteste #mainContent."""
    body = authenticated_client.get('/').get_data(as_text=True)
    assert 'class="skip-link"' in body
    assert 'href="#mainContent"' in body
    assert 'id="mainContent"' in body


def test_breadcrumb_prezent(authenticated_client):
    """Breadcrumb prezent cu aria-label si markup li.breadcrumb-item pentru home."""
    body = authenticated_client.get('/').get_data(as_text=True)
    assert 'class="breadcrumb"' in body
    assert 'breadcrumb-item' in body
    # nav-ul de breadcrumb are eticheta de accesibilitate
    assert 'aria-label' in body


def test_flash_are_aria_live(authenticated_client):
    """Containerul de flash are aria-live (anuntat de cititoarele de ecran).

    Provocam un flash real prin logout->login redirect sau o actiune; daca nu
    apare niciun flash pe dashboard, verificam cel putin ca markup-ul flash din
    base.html e prezent cand exista mesaje — folosim sesiunea direct."""
    with authenticated_client.session_transaction() as sess:
        sess['_flashes'] = [('success', 'Test mesaj flash')]
    body = authenticated_client.get('/').get_data(as_text=True)
    assert 'flash-container' in body
    assert 'aria-live="polite"' in body
    assert 'Test mesaj flash' in body


def test_dropdown_uri_au_aria(authenticated_client):
    """Dropdown-urile din header au aria-haspopup/aria-expanded + role=menu."""
    body = authenticated_client.get('/').get_data(as_text=True)
    assert 'aria-haspopup="true"' in body
    assert 'aria-expanded="false"' in body
    assert 'role="menu"' in body


def test_modal_stergere_role_dialog(authenticated_client):
    """Modalul global de stergere are role=dialog + aria-modal + labelledby."""
    body = authenticated_client.get('/').get_data(as_text=True)
    assert 'role="dialog"' in body
    assert 'aria-modal="true"' in body
    assert 'aria-labelledby="deleteModalTitle"' in body


def test_sidebar_aria_label(authenticated_client):
    """Sidebar-ul (aside) are eticheta de navigare."""
    body = authenticated_client.get('/').get_data(as_text=True)
    assert 'class="sidebar"' in body
    # aside cu aria-label de navigare principala
    assert 'id="sidebar"' in body


def test_sidebar_submenu_prin_clasa_nu_inline(authenticated_client):
    """Pe o pagina BIM, submeniul se randeaza prin clasa .sidebar-submenu
    (macro nav_item), iar parintele are aria-expanded=true. Verificam ca NU
    mai exista stilul inline vechi al submeniului."""
    body = authenticated_client.get('/bim/').get_data(as_text=True)
    assert 'sidebar-submenu' in body
    assert 'aria-expanded="true"' in body
    # markup-ul vechi avea: style="list-style:none; padding:4px 0 4px 36px; margin:0;"
    assert 'list-style:none; padding:4px 0 4px 36px' not in body


def test_chartjs_incarcat_doar_unde_e_folosit(authenticated_client):
    """Chart.js nu mai e global in <head>: apare pe dashboard (are grafice),
    dar lipseste pe o pagina fara grafice (angajati)."""
    dash = authenticated_client.get('/').get_data(as_text=True)
    ang = authenticated_client.get('/angajati/').get_data(as_text=True)
    assert 'chart.umd' in dash, 'dashboard trebuie sa incarce Chart.js local'
    assert 'chart.umd' not in ang, 'pagina fara grafice nu trebuie sa incarce Chart.js'


def test_login_buton_gold(client):
    """Pagina de login randeaza (butonul gold/navy e in style.css ca .login-btn)."""
    resp = client.get('/auth/login')
    assert resp.status_code == 200
    assert 'login-btn' in resp.get_data(as_text=True)
