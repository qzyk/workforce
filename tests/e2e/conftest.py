"""
Conftest pentru E2E tests cu Playwright.

Pornest serverul Flask in background (subprocess) pe port 5099,
ruleaza testele cu browser real, opreste server la final.

Pentru rulare:
    pip install pytest-playwright
    playwright install chromium
    pytest tests/e2e/ -m e2e

Pentru CI: skip default. Rulare explicita cu PLAYWRIGHT_E2E=1.
"""

import os
import socket
import subprocess
import sys
import tempfile
import time
import pytest

E2E_PORT = 5099
E2E_BASE_URL = f'http://127.0.0.1:{E2E_PORT}'


def _wait_for_port(port, host='127.0.0.1', timeout=15):
    """Astept ca portul sa accepte conexiuni."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(0.3)
    return False


@pytest.fixture(scope='session')
def e2e_server():
    """
    Porneste serverul Flask pe port 5099 cu DB temporar.
    Yield base URL. Opreste serverul la final.
    """
    if os.environ.get('PLAYWRIGHT_E2E') != '1':
        pytest.skip('E2E tests dezactivate. Setati PLAYWRIGHT_E2E=1 pentru a le rula.')

    # DB temporar
    fd, db_path = tempfile.mkstemp(suffix='.db', prefix='workforce_e2e_')
    os.close(fd)

    # Initializez DB cu un admin
    env = os.environ.copy()
    env['DATABASE_URL'] = f'sqlite:///{db_path}'
    env['SECRET_KEY'] = 'e2e-test-key'
    env['FLASK_APP'] = 'app.py'

    # Repo root
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # Init DB cu admin de test
    init_script = '''
import os, sys
sys.path.insert(0, ".")
from app import create_app
from models import db, Utilizator, Proiect, Angajat
from datetime import date
app = create_app("default")
with app.app_context():
    db.create_all()
    if not Utilizator.query.filter_by(email="e2e_admin@test.local").first():
        u = Utilizator(nume="E2E", prenume="Admin", email="e2e_admin@test.local",
                       rol="admin", activ=True)
        u.set_password("e2e_pass_123")
        db.session.add(u)
    if not Proiect.query.filter_by(cod_proiect="PRJ-E2E").first():
        p = Proiect(cod_proiect="PRJ-E2E", nume="Proiect E2E",
                    data_start=date(2025,1,1), status="activ")
        db.session.add(p)
    if not Angajat.query.filter_by(cnp="9900101000001").first():
        a = Angajat(cnp="9900101000001", nume="E2E", prenume="Angajat",
                    functie="Inginer", data_angajare=date(2024,1,1), status="activ")
        db.session.add(a)
    db.session.commit()
'''
    subprocess.run([sys.executable, '-c', init_script], env=env, cwd=repo_root, check=True)

    # Pornesc server in background
    server_proc = subprocess.Popen(
        [sys.executable, '-c',
         f'import os; os.environ["DATABASE_URL"] = "sqlite:///{db_path}"; '
         f'import sys; sys.path.insert(0, "."); '
         f'from app import app; app.run(host="127.0.0.1", port={E2E_PORT}, debug=False, use_reloader=False)'],
        env=env, cwd=repo_root,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    if not _wait_for_port(E2E_PORT):
        server_proc.terminate()
        os.unlink(db_path)
        pytest.fail(f'Serverul E2E nu a pornit pe port {E2E_PORT}')

    yield E2E_BASE_URL

    server_proc.terminate()
    try:
        server_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server_proc.kill()
    try:
        os.unlink(db_path)
    except OSError:
        pass
