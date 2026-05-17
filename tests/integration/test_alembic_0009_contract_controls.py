"""
Test specific pentru migratia 0009 (Contract Controls - Faza 9):
  - Upgrade head pe DB fresh creeaza toate cele 19 tabele Faza 9
  - Downgrade 0009 -> 0008 le sterge curat (zero ramase)
  - Re-upgrade le re-creeaza

Verifica izolat 0009. Paritatea generala Alembic <-> models e acoperita
de test_alembic_baseline_matches_models in test_alembic_baseline.py.
"""

import os
import subprocess
import sys
import sqlite3
import tempfile

import pytest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


FAZA9_TABLES = {
    'contracte', 'termeni_contract', 'termeni_urmariti',
    'programe_referinta', 'taskuri_program',
    'oferte_contract', 'pozitii_boq', 'cantitati_executate_lunare',
    'situatii_lunare', 'rapoarte_lucrari_proiect',
    'corespondente', 'revendicari',
    'revendicari_termeni', 'revendicari_taskuri', 'revendicari_cantitati',
    'procese_verbale', 'anexe', 'notificari_app',
    'reguli_notificare_proiect',
}


def _alembic(db_path: str, *args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env['DATABASE_URL'] = f'sqlite:///{db_path}'
    return subprocess.run(
        [sys.executable, '-m', 'alembic', *args],
        env=env, cwd=REPO_ROOT, capture_output=True, text=True,
    )


def _table_names(db_path: str) -> set:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


@pytest.fixture
def fresh_db():
    fd, path = tempfile.mkstemp(suffix='.db', prefix='test_0009_')
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


def test_upgrade_head_creates_all_19_faza9_tables(fresh_db):
    r = _alembic(fresh_db, 'upgrade', 'head')
    assert r.returncode == 0, f'upgrade esuat: {r.stderr}'
    tables = _table_names(fresh_db)
    missing = FAZA9_TABLES - tables
    assert not missing, f'Tabele Faza 9 lipsa dupa upgrade head: {missing}'


def test_downgrade_0009_removes_all_faza9_tables(fresh_db):
    # Upgrade pana la 0009
    assert _alembic(fresh_db, 'upgrade', 'head').returncode == 0
    pre = _table_names(fresh_db)
    assert FAZA9_TABLES.issubset(pre)

    # Downgrade 0009 -> 0008
    r = _alembic(fresh_db, 'downgrade', '0008_governance')
    assert r.returncode == 0, f'downgrade esuat: {r.stderr}'
    post = _table_names(fresh_db)
    leaked = FAZA9_TABLES & post
    assert not leaked, f'Tabele Faza 9 ramase dupa downgrade: {leaked}'


def test_upgrade_downgrade_upgrade_roundtrip(fresh_db):
    # 1. Upgrade head
    assert _alembic(fresh_db, 'upgrade', 'head').returncode == 0
    assert FAZA9_TABLES.issubset(_table_names(fresh_db))
    # 2. Downgrade 0008
    assert _alembic(fresh_db, 'downgrade', '0008_governance').returncode == 0
    assert not (FAZA9_TABLES & _table_names(fresh_db))
    # 3. Re-upgrade head
    assert _alembic(fresh_db, 'upgrade', 'head').returncode == 0
    assert FAZA9_TABLES.issubset(_table_names(fresh_db))


def test_alembic_current_at_0009_after_upgrade(fresh_db):
    assert _alembic(fresh_db, 'upgrade', 'head').returncode == 0
    r = _alembic(fresh_db, 'current')
    assert r.returncode == 0
    assert '0009_contract_controls' in r.stdout, (
        f'Revision-ul curent nu e 0009: {r.stdout!r}'
    )
