"""
Test paritate: schema produsa de 'alembic upgrade head' pe DB gol
trebuie sa fie identica cu schema generata de db.create_all() din models.

Asta garanteaza ca baseline-ul Alembic reflecta exact modelele curente.
Daca cineva modifica un model fara sa genereze o migratie, acest test
prinde inconsistenta.
"""

import os
import subprocess
import sys
import tempfile

import pytest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _run_alembic_upgrade(db_path: str) -> None:
    """Ruleaza 'alembic upgrade head' pe DB-ul dat."""
    env = os.environ.copy()
    env['DATABASE_URL'] = f'sqlite:///{db_path}'
    result = subprocess.run(
        [sys.executable, '-m', 'alembic', 'upgrade', 'head'],
        env=env, cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f'alembic upgrade head a esuat:\n'
        f'STDOUT: {result.stdout}\nSTDERR: {result.stderr}'
    )


def _get_table_names(db_path: str) -> set:
    """Extrage numele de tabele dintr-un DB SQLite."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


def _get_columns_for_table(db_path: str, table: str) -> set:
    """Extrage (col_name, col_type, notnull, pk) pentru o tabela."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(f'PRAGMA table_info("{table}")')
        return {
            (row[1], row[2].upper(), int(row[3]), int(row[5]))
            for row in cur.fetchall()
        }
    finally:
        conn.close()


def test_alembic_baseline_matches_models():
    """
    Schema produsa de migratiile Alembic trebuie sa fie identica cu cea
    produsa de db.create_all() pe baza modelelor.
    """
    # 1) DB cu Alembic
    fd1, alembic_db = tempfile.mkstemp(suffix='.db', prefix='test_alembic_')
    os.close(fd1)
    # 2) DB cu db.create_all()
    fd2, models_db = tempfile.mkstemp(suffix='.db', prefix='test_models_')
    os.close(fd2)

    try:
        _run_alembic_upgrade(alembic_db)

        # Build schema din modele intr-un proces curat (ca sa nu interfere
        # cu app-ul deja configurat).
        env = os.environ.copy()
        env['DATABASE_URL'] = f'sqlite:///{models_db}'
        env['SECRET_KEY'] = 'test-key'
        env['WTF_CSRF_ENABLED'] = '0'
        script = (
            'import sys; sys.path.insert(0, ".");'
            'from app import create_app; from models import db;'
            'app = create_app("default");'
            'app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///' + models_db + '";'
            'ctx = app.app_context(); ctx.push();'
            'db.create_all(); ctx.pop();'
        )
        result = subprocess.run(
            [sys.executable, '-c', script],
            env=env, cwd=REPO_ROOT, capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f'create_all a esuat:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}'
        )

        # Comparam tabelele (excludem alembic_version din partea Alembic)
        alembic_tables = _get_table_names(alembic_db) - {'alembic_version'}
        model_tables = _get_table_names(models_db)

        only_in_alembic = alembic_tables - model_tables
        only_in_models = model_tables - alembic_tables

        assert not only_in_alembic, (
            f'Tabele in Alembic dar NU in modele: {only_in_alembic}'
        )
        assert not only_in_models, (
            f'Tabele in modele dar NU in Alembic baseline: {only_in_models}. '
            f'Genereaza o noua migratie cu: alembic revision --autogenerate -m "..."'
        )

        # Pentru fiecare tabela, comparam coloanele
        diffs = []
        for table in sorted(alembic_tables):
            a_cols = _get_columns_for_table(alembic_db, table)
            m_cols = _get_columns_for_table(models_db, table)
            if a_cols != m_cols:
                diffs.append((table, a_cols ^ m_cols))

        assert not diffs, (
            f'Diferente coloane intre Alembic si modele:\n'
            + '\n'.join(f'  {t}: {d}' for t, d in diffs)
        )
    finally:
        for p in (alembic_db, models_db):
            try:
                os.unlink(p)
            except OSError:
                pass


def test_alembic_current_after_upgrade_is_at_head():
    """Dupa 'alembic upgrade head', revision-ul curent trebuie sa fie marcat (head)."""
    fd, db_path = tempfile.mkstemp(suffix='.db', prefix='test_alembic_cur_')
    os.close(fd)
    try:
        _run_alembic_upgrade(db_path)

        env = os.environ.copy()
        env['DATABASE_URL'] = f'sqlite:///{db_path}'
        result = subprocess.run(
            [sys.executable, '-m', 'alembic', 'current'],
            env=env, cwd=REPO_ROOT, capture_output=True, text=True,
        )
        assert result.returncode == 0
        # Indiferent ce migratii au fost adaugate, dupa upgrade head trebuie sa fim la (head)
        assert '(head)' in result.stdout, (
            f'DB nu e la head dupa upgrade. Output: {result.stdout!r}'
        )
    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass


def test_alembic_baseline_revision_is_first():
    """Verific ca exista 'alembic history' si baseline-ul (0001_baseline) e radacina."""
    env = os.environ.copy()
    env['DATABASE_URL'] = 'sqlite:///:memory:'
    result = subprocess.run(
        [sys.executable, '-m', 'alembic', 'history'],
        env=env, cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert '0001_baseline' in result.stdout, (
        f'baseline 0001_baseline lipseste din history: {result.stdout!r}'
    )
