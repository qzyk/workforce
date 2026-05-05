"""
E2E tests pe MySQL - 5 critical journeys cu Playwright.

Pentru rulare:
    docker compose -f docker-compose.test.yml up -d
    export MYSQL_TEST_URL='mysql+pymysql://workforce:workforce_pass@127.0.0.1:3307/workforce_test'
    PLAYWRIGHT_E2E=1 pytest tests/e2e/test_critical_journeys_mysql.py -v

Skip default (PLAYWRIGHT_E2E nu setat).
"""

import os
import socket
import subprocess
import sys
import time
import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.mysql]

E2E_PORT = 5098  # diferit de cel din test_critical_journeys.py
E2E_BASE_URL = f'http://127.0.0.1:{E2E_PORT}'


def _wait_for_port(port, host='127.0.0.1', timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(0.3)
    return False


@pytest.fixture(scope='module')
def mysql_e2e_server():
    """Server Flask pe MySQL pentru E2E."""
    if os.environ.get('PLAYWRIGHT_E2E') != '1':
        pytest.skip('E2E dezactivate (PLAYWRIGHT_E2E nu e 1)')

    mysql_url = os.environ.get('MYSQL_TEST_URL')
    if not mysql_url:
        pytest.skip('MYSQL_TEST_URL nu e setat')

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    env = os.environ.copy()
    env['DATABASE_URL'] = mysql_url
    env['SECRET_KEY'] = 'e2e-mysql-key'
    env['FLASK_APP'] = 'app.py'

    # Init DB cu admin de test + un proiect / angajat
    init_script = '''
import os, sys
sys.path.insert(0, ".")
from app import create_app
from models import db, Utilizator, Proiect, Angajat
from datetime import date
app = create_app("default")
with app.app_context():
    db.drop_all()
    db.create_all()
    u = Utilizator(nume="E2E", prenume="MyAdmin", email="e2e_my@test.local",
                   rol="admin", activ=True)
    u.set_password("e2e_my_123")
    db.session.add(u)
    p = Proiect(cod_proiect="PRJ-E2E-MY", nume="Proiect E2E MySQL",
                data_start=date(2025,1,1), status="activ")
    a = Angajat(cnp="9900202000001", nume="E2E", prenume="MyAng",
                functie="Inginer", data_angajare=date(2024,1,1), status="activ")
    db.session.add(p); db.session.add(a)
    db.session.commit()
'''
    subprocess.run([sys.executable, '-c', init_script], env=env, cwd=repo_root, check=True)

    server_proc = subprocess.Popen(
        [sys.executable, '-c',
         f'import os; os.environ["DATABASE_URL"] = "{mysql_url}"; '
         f'import sys; sys.path.insert(0, "."); '
         f'from app import app; app.run(host="127.0.0.1", port={E2E_PORT}, debug=False, use_reloader=False)'],
        env=env, cwd=repo_root,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    if not _wait_for_port(E2E_PORT):
        server_proc.terminate()
        pytest.fail(f'E2E MySQL server nu a pornit pe port {E2E_PORT}')

    yield E2E_BASE_URL

    server_proc.terminate()
    try:
        server_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server_proc.kill()


def _login_admin_my(page, base_url):
    page.goto(f'{base_url}/auth/login')
    page.fill('input[name="email"]', 'e2e_my@test.local')
    page.fill('input[name="parola"]', 'e2e_my_123')
    page.click('button[type="submit"]')


# ============================================================
# E2E flows pe MySQL
# ============================================================

def test_e2e_my_login(mysql_e2e_server, page):
    """1. Login pe MySQL."""
    page.goto(f'{mysql_e2e_server}/auth/login')
    page.fill('input[name="email"]', 'e2e_my@test.local')
    page.fill('input[name="parola"]', 'e2e_my_123')
    page.click('button[type="submit"]')
    page.wait_for_url('**/dashboard**', timeout=5000)


def test_e2e_my_creeaza_activitate(mysql_e2e_server, page):
    """2. Creare activitate workforce pe MySQL."""
    _login_admin_my(page, mysql_e2e_server)
    page.goto(f'{mysql_e2e_server}/activitati/adauga')
    page.wait_for_load_state('networkidle')

    page.select_option('select[name="angajat_id"]', label_pattern='E2E')
    page.select_option('select[name="proiect_ids[]"]', label_pattern='PRJ-E2E-MY')
    page.fill('textarea[name="activitate_principala"]', 'E2E_MY_TEST_ACT')

    page.click('button[name="actiune"][value="draft"]')
    page.wait_for_load_state('networkidle')

    page.goto(f'{mysql_e2e_server}/activitati/')
    assert page.locator('text=E2E_MY_TEST_ACT').count() > 0


def test_e2e_my_export_innova_modal(mysql_e2e_server, page):
    """3. Modal Export INNOVA pe MySQL."""
    _login_admin_my(page, mysql_e2e_server)
    page.goto(f'{mysql_e2e_server}/activitati/')

    page.click('button:has-text("Export INNOVA")')
    modal = page.locator('#exportInnovaModal')
    assert modal.is_visible()


def test_e2e_my_creeaza_santier_bim(mysql_e2e_server, page):
    """4. Creare santier BIM pe MySQL."""
    _login_admin_my(page, mysql_e2e_server)
    page.goto(f'{mysql_e2e_server}/bim/santier/nou')

    page.fill('input[name="cod"]', 'E2E-MY-SITE')
    page.fill('input[name="nume"]', 'E2E MySQL Santier')
    page.fill('input[name="oras"]', 'București')

    page.click('button[type="submit"]:has-text("Salveaza")')
    page.wait_for_load_state('networkidle')

    page.goto(f'{mysql_e2e_server}/bim/santiere')
    assert page.locator('text=E2E-MY-SITE').count() > 0
    # Verifica diacritice pastrate
    assert page.locator('text=București').count() > 0


def test_e2e_my_bim_dashboard(mysql_e2e_server, page):
    """5. Dashboard BIM se incarca corect cu MySQL backend."""
    _login_admin_my(page, mysql_e2e_server)
    page.goto(f'{mysql_e2e_server}/bim/')
    page.wait_for_load_state('networkidle')
    assert page.locator('text=BIM').count() > 0
