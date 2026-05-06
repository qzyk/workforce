"""
E2E smoke tests pentru Faza 1 BIM foundation.

Acopera:
1) Navigare admin -> dashboard BIM (verifica routing-ul si pagina de baza).
2) Creare santier prin UI -> audit log inregistreaza actiunea.

Default: SKIP. Rulare explicita cu PLAYWRIGHT_E2E=1.
"""

import pytest

pytestmark = pytest.mark.e2e


def _login_admin(page, base_url):
    page.goto(f'{base_url}/auth/login')
    page.fill('input[name="email"]', 'e2e_admin@test.local')
    page.fill('input[name="parola"]', 'e2e_pass_123')
    page.click('button[type="submit"]')
    page.wait_for_url('**/dashboard**', timeout=5000)


def test_smoke_bim_dashboard_renders(e2e_server, page):
    """Admin se logheaza si poate naviga la dashboard-ul BIM fara erori."""
    _login_admin(page, e2e_server)
    page.goto(f'{e2e_server}/bim/')
    page.wait_for_load_state('networkidle', timeout=5000)
    # Status 200 + cuvant cheie BIM in pagina (titlu sau heading)
    body_text = page.locator('body').inner_text().lower()
    assert 'bim' in body_text or 'santier' in body_text, (
        'Pagina /bim/ nu pare sa fie dashboard-ul BIM.'
    )


def test_smoke_create_santier_writes_audit_log(e2e_server, page):
    """Crearea unui santier prin UI insereaza un rand in audit_log (action=create)."""
    _login_admin(page, e2e_server)

    # Navigare la formular nou santier
    page.goto(f'{e2e_server}/bim/santier/nou')
    page.wait_for_load_state('networkidle', timeout=5000)

    # Completare formular minimal
    cod_unic = 'E2E_PHASE1_AUD'
    page.fill('input[name="cod"]', cod_unic)
    page.fill('input[name="nume"]', 'Santier Smoke Audit')
    page.click('button[type="submit"]')

    # Dupa redirect, verificam DB direct prin API/admin sau prin endpoint
    # (foarte simplu: navigam la lista santiere si vedem codul)
    page.goto(f'{e2e_server}/bim/santiere')
    page.wait_for_load_state('networkidle')
    assert cod_unic in page.locator('body').inner_text(), (
        f'Codul santierului {cod_unic} nu apare in lista.'
    )

    # Verificam audit log via shell script (rulam Python in subprocess)
    import os, subprocess, sys
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    db_url = os.environ.get('DATABASE_URL', '')
    if not db_url:
        pytest.skip('DATABASE_URL not set, sar verificarea DB direct')

    script = (
        'import sys; sys.path.insert(0, ".");'
        'from app import create_app; from models import db, AuditLog;'
        'app = create_app("default");'
        'ctx = app.app_context(); ctx.push();'
        'rows = AuditLog.query.filter_by(entity_type="santier", action="create").count();'
        'print(rows)'
    )
    env = os.environ.copy()
    result = subprocess.run(
        [sys.executable, '-c', script],
        env=env, cwd=repo_root, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    count = int(result.stdout.strip())
    assert count >= 1, f'audit_log nu contine intrari de tip create pentru santier (count={count})'
