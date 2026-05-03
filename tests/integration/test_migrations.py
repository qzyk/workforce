"""
Tests pentru CLI-urile de migrare (idempotency, no errors la re-rulare).
"""

import pytest
from click.testing import CliRunner


class TestMigrateActivitati:
    def test_migrate_activitati_idempotent(self, app):
        """A doua rulare nu trebuie sa adauge nimic nou."""
        from app import create_app
        runner = CliRunner()
        with app.app_context():
            # Prima rulare
            result1 = runner.invoke(app.cli, ['migrate-activitati'])
            assert result1.exit_code == 0

            # A doua rulare - toate trebuie sa fie [SKIP]
            result2 = runner.invoke(app.cli, ['migrate-activitati'])
            assert result2.exit_code == 0
            assert '[SKIP]' in result2.output
            assert '0 coloane noi' in result2.output


class TestMigrateBim:
    def test_migrate_bim_idempotent(self, app):
        """migrate-bim ruleaza fara erori la run repetat."""
        runner = CliRunner()
        with app.app_context():
            result = runner.invoke(app.cli, ['migrate-bim'])
            assert result.exit_code == 0
            # Toate FK-urile sunt deja prezente -> SKIP-uri
            assert 'Migrare BIM completa' in result.output

    def test_migrate_bim_creates_all_tables(self, app):
        from sqlalchemy import inspect
        from models import db
        with app.app_context():
            insp = inspect(db.engine)
            tables = set(insp.get_table_names())
            expected_bim = {
                'bim_santiere', 'bim_cladiri', 'bim_niveluri',
                'bim_zone', 'bim_spatii', 'bim_elemente',
                'bim_assets', 'bim_issues', 'bim_modele',
                'bim_external_mappings', 'tenants',
            }
            missing = expected_bim - tables
            assert not missing, f'Tabele BIM lipsa: {missing}'


class TestValidateBim:
    def test_validate_bim_runs(self, app):
        runner = CliRunner()
        with app.app_context():
            result = runner.invoke(app.cli, ['validate-bim'])
            assert result.exit_code == 0
            assert 'BIM Data Quality Report' in result.output

    def test_validate_bim_exit_code_flag_on_clean_db(self, app):
        """DB curata -> validate-bim --exit-code returneaza 0."""
        from models import db
        runner = CliRunner()
        with app.app_context():
            # Asigur DB curat (cleanup auto a sters totul deja)
            result = runner.invoke(app.cli, ['validate-bim', '--exit-code'])
            assert result.exit_code == 0
