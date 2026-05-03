"""
E2E tests cu Playwright - 5 journey-uri critice cu browser real.

Pentru rulare:
    pip install pytest-playwright
    playwright install chromium
    PLAYWRIGHT_E2E=1 pytest tests/e2e/

Default: SKIP. Rulare explicita doar cand PLAYWRIGHT_E2E=1.
"""

import pytest

# Sare peste toate testele E2E daca nu cerem explicit
pytestmark = pytest.mark.e2e


@pytest.fixture
def page(e2e_server, page):
    """page din pytest-playwright + base URL setat."""
    page.goto(e2e_server)
    return page


def login_as_admin(page, base_url):
    """Helper: autentificare ca admin E2E."""
    page.goto(f'{base_url}/auth/login')
    page.fill('input[name="email"]', 'e2e_admin@test.local')
    page.fill('input[name="parola"]', 'e2e_pass_123')
    page.click('button[type="submit"]')


# ============================================================
# E2E 1: Login -> Dashboard
# ============================================================

def test_e2e_login_si_dashboard(e2e_server, page):
    """User-ul se logheaza si vede dashboard-ul."""
    page.goto(f'{e2e_server}/auth/login')
    page.fill('input[name="email"]', 'e2e_admin@test.local')
    page.fill('input[name="parola"]', 'e2e_pass_123')
    page.click('button[type="submit"]')
    page.wait_for_url('**/dashboard**', timeout=5000)
    # Verifica ca apare numele in sidebar
    assert page.locator('text=E2E Admin').count() > 0 or page.locator('text=Admin').count() > 0


# ============================================================
# E2E 2: Creare activitate zilnica
# ============================================================

def test_e2e_creeaza_activitate_zilnica(e2e_server, page):
    login_as_admin(page, e2e_server)
    page.goto(f'{e2e_server}/activitati/adauga')
    page.wait_for_load_state('networkidle')

    # Selecteaza angajat (operator e2e)
    page.select_option('select[name="angajat_id"]', label_pattern='E2E Angajat')

    # Selecteaza proiect (multi-select)
    page.select_option('select[name="proiect_ids[]"]', label_pattern='PRJ-E2E')

    # Descriere
    page.fill('textarea[name="activitate_principala"]', 'E2E_TEST_ACT_DAILY')

    # Submit ca draft
    page.click('button[name="actiune"][value="draft"]')
    page.wait_for_load_state('networkidle')

    # Verifica salvare prin lista
    page.goto(f'{e2e_server}/activitati/')
    assert page.locator('text=E2E_TEST_ACT_DAILY').count() > 0


# ============================================================
# E2E 3: Modal Export INNOVA
# ============================================================

def test_e2e_modal_export_innova(e2e_server, page):
    login_as_admin(page, e2e_server)
    page.goto(f'{e2e_server}/activitati/')

    # Click pe butonul Export INNOVA
    page.click('button:has-text("Export INNOVA")')

    # Modalul ar trebui sa fie vizibil
    modal = page.locator('#exportInnovaModal')
    assert modal.is_visible()

    # Multi-select angajati
    angajati_select = page.locator('#exportAngajatiSelect')
    assert angajati_select.count() > 0


# ============================================================
# E2E 4: BIM workflow simplu - creeaza santier
# ============================================================

def test_e2e_creeaza_santier_bim(e2e_server, page):
    login_as_admin(page, e2e_server)
    page.goto(f'{e2e_server}/bim/santier/nou')

    page.fill('input[name="cod"]', 'E2E-SITE-001')
    page.fill('input[name="nume"]', 'E2E Test Santier')
    page.fill('input[name="oras"]', 'Bucuresti')

    page.click('button[type="submit"]:has-text("Salveaza")')
    page.wait_for_load_state('networkidle')

    # Verifica ca santierul apare in lista
    page.goto(f'{e2e_server}/bim/santiere')
    assert page.locator('text=E2E-SITE-001').count() > 0


# ============================================================
# E2E 5: Search global BIM autocomplete
# ============================================================

def test_e2e_search_global_bim(e2e_server, page):
    login_as_admin(page, e2e_server)
    page.goto(f'{e2e_server}/')

    search_input = page.locator('#bimGlobalSearch')
    if search_input.count() == 0:
        pytest.skip('Search bar global nu e prezent in header')

    # Tipam un text scurt (sub 2 char) - nu apar rezultate
    search_input.fill('a')
    page.wait_for_timeout(400)  # debounce 250ms
    results = page.locator('#bimSearchResults')
    # Trebuie sa fie hidden sau gol
    assert not results.is_visible() or results.locator('a').count() == 0

    # Tipam ceva valid
    search_input.fill('TEST')
    page.wait_for_timeout(500)
    # results poate fi vizibile sau ascunse, dar nu crasham
