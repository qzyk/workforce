"""
Dual-mode test runner: re-ruleaza testele cheie pe MySQL.

In loc sa duplicam toate cele 190 teste cu @pytest.mark.mysql, folosim subprocess
ca sa lansam pytest-ul intr-un proces nou cu DATABASE_URL pe MySQL.
Aceasta abordare e simpla si nu cere refactor major.

Rulat in CI cu service container MySQL.
Local: setezi MYSQL_TEST_URL si ruleaza:
    pytest tests/integration/test_mysql_existing_suite_runner.py -v -s
"""

import os
import subprocess
import sys
import pytest

pytestmark = pytest.mark.mysql


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _run_pytest_with_mysql(test_paths, mysql_url):
    """Lanseaza pytest intr-un subprocess cu DATABASE_URL=MYSQL."""
    env = os.environ.copy()
    env['DATABASE_URL'] = mysql_url
    env['MYSQL_TEST_URL'] = mysql_url
    env['SECRET_KEY'] = 'mysql-dual-test'
    env['WTF_CSRF_ENABLED'] = '0'
    cmd = [sys.executable, '-m', 'pytest', '--tb=short', '-q'] + test_paths
    result = subprocess.run(
        cmd, env=env, cwd=REPO_ROOT,
        capture_output=True, text=True, timeout=180,
    )
    return result


class TestSuiteOnMySQL:
    """Re-rulare suite-uri cheie pe MySQL prin subprocess."""

    def test_smoke_passes_on_mysql(self):
        """Testul smoke (login, redirect, route registry) trebuie sa treaca pe MySQL."""
        mysql_url = os.environ.get('MYSQL_TEST_URL')
        result = _run_pytest_with_mysql(
            ['tests/integration/test_smoke.py'], mysql_url
        )
        if result.returncode != 0:
            pytest.fail(
                f'Smoke tests FAIL on MySQL.\n'
                f'STDOUT:\n{result.stdout}\n'
                f'STDERR:\n{result.stderr}'
            )

    def test_workforce_activitati_on_mysql(self):
        """CRUD activitati + workflow draft->aprobat trebuie sa mearga pe MySQL."""
        mysql_url = os.environ.get('MYSQL_TEST_URL')
        result = _run_pytest_with_mysql(
            ['tests/integration/test_workforce_activitati.py'], mysql_url
        )
        if result.returncode != 0:
            pytest.fail(
                f'Workforce activitati tests FAIL on MySQL.\n'
                f'STDOUT:\n{result.stdout}\n'
                f'STDERR:\n{result.stderr}'
            )

    def test_bim_routes_on_mysql(self):
        mysql_url = os.environ.get('MYSQL_TEST_URL')
        result = _run_pytest_with_mysql(
            ['tests/integration/test_bim_routes.py'], mysql_url
        )
        if result.returncode != 0:
            pytest.fail(
                f'BIM routes tests FAIL on MySQL.\n'
                f'STDOUT:\n{result.stdout[-3000:]}'
            )

    def test_bim_workforce_link_on_mysql(self):
        mysql_url = os.environ.get('MYSQL_TEST_URL')
        result = _run_pytest_with_mysql(
            ['tests/integration/test_bim_workforce_link.py'], mysql_url
        )
        if result.returncode != 0:
            pytest.fail(
                f'BIM x workforce link tests FAIL on MySQL.\n'
                f'STDOUT:\n{result.stdout[-3000:]}'
            )

    def test_export_edifico_on_mysql(self):
        mysql_url = os.environ.get('MYSQL_TEST_URL')
        result = _run_pytest_with_mysql(
            ['tests/integration/test_workforce_export_edifico.py'], mysql_url
        )
        if result.returncode != 0:
            pytest.fail(
                f'Export EDIFICO tests FAIL on MySQL.\n'
                f'STDOUT:\n{result.stdout[-3000:]}'
            )

    def test_data_quality_on_mysql(self):
        mysql_url = os.environ.get('MYSQL_TEST_URL')
        result = _run_pytest_with_mysql(
            ['tests/integration/test_bim_data_quality.py'], mysql_url
        )
        if result.returncode != 0:
            pytest.fail(
                f'Data quality tests FAIL on MySQL.\n'
                f'STDOUT:\n{result.stdout[-3000:]}'
            )

    def test_permissions_on_mysql(self):
        mysql_url = os.environ.get('MYSQL_TEST_URL')
        result = _run_pytest_with_mysql(
            ['tests/integration/test_permissions.py'], mysql_url
        )
        if result.returncode != 0:
            pytest.fail(
                f'Permissions tests FAIL on MySQL.\n'
                f'STDOUT:\n{result.stdout[-3000:]}'
            )

    def test_tenants_crud_on_mysql(self):
        mysql_url = os.environ.get('MYSQL_TEST_URL')
        result = _run_pytest_with_mysql(
            ['tests/integration/test_tenants_crud.py'], mysql_url
        )
        if result.returncode != 0:
            pytest.fail(
                f'Tenants CRUD tests FAIL on MySQL.\n'
                f'STDOUT:\n{result.stdout[-3000:]}'
            )
