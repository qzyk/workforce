"""Teste Tema E (Ops): serviciu backup automat + CLI + rute + diagnostics ops."""
import os
import sqlite3


def test_backup_creeaza_lista_status(app, tmp_path, monkeypatch):
    """creeaza_backup face o copie consistenta; lista + status o vad."""
    from services import backup
    src = tmp_path / 'src.db'
    sqlite3.connect(str(src)).close()       # DB sursa goala, valida
    bdir = tmp_path / 'bks'
    bdir.mkdir()
    monkeypatch.setattr(backup, 'cale_db', lambda: str(src))
    monkeypatch.setattr(backup, 'dir_backups', lambda: str(bdir))

    with app.app_context():
        r = backup.creeaza_backup('test')
        assert r['ok'] and r['nume'].startswith('workforce_test_')
        assert os.path.exists(r['path'])
        bks = backup.lista_backups()
        assert any(b['nume'] == r['nume'] for b in bks)
        st = backup.status()
        assert st['nr'] >= 1 and st['sqlite'] is True


def test_backup_roteste_pastreaza_doar_auto(app, tmp_path, monkeypatch):
    """roteste pastreaza ultimele N 'auto'; manualele NU se ating."""
    from services import backup
    bdir = tmp_path / 'bks'
    bdir.mkdir()
    for i in range(1, 6):
        (bdir / f'workforce_auto_2026010{i}_000000.db').write_bytes(b'x')
    (bdir / 'workforce_manual_20260101_000000.db').write_bytes(b'x')
    monkeypatch.setattr(backup, 'dir_backups', lambda: str(bdir))

    n = backup.roteste(maxim=2)
    assert n == 3
    ramase = sorted(p.name for p in bdir.iterdir())
    autos = [r for r in ramase if r.startswith('workforce_auto_')]
    assert len(autos) == 2 and autos == ['workforce_auto_20260104_000000.db',
                                         'workforce_auto_20260105_000000.db']
    assert 'workforce_manual_20260101_000000.db' in ramase   # manualul intact


def test_backup_mysql_graceful(app, monkeypatch):
    """Pe MySQL (cale_db None) backup-ul nu crapa, intoarce ok=False explicat."""
    from services import backup
    monkeypatch.setattr(backup, 'cale_db', lambda: None)
    with app.app_context():
        r = backup.creeaza_backup('auto')
        assert r['ok'] is False and 'MySQL' in r['mesaj']


def test_cli_backup(app):
    """`flask backup` ruleaza si raporteaza OK; curat fisierul creat."""
    from services import backup
    runner = app.test_cli_runner()
    with app.app_context():
        bdir = backup.dir_backups()
        inainte = {b['nume'] for b in backup.lista_backups()}
    res = runner.invoke(args=['backup', '--eticheta', 'clitest'])
    assert res.exit_code == 0 and '[OK]' in res.output
    with app.app_context():
        noi = [b for b in backup.lista_backups()
               if b['nume'] not in inainte and 'clitest' in b['nume']]
    for b in noi:
        try:
            os.remove(os.path.join(bdir, b['nume']))
        except OSError:
            pass
    assert len(noi) >= 1


def test_ruta_backup_pagina(authenticated_client):
    r = authenticated_client.get('/setari/backup')
    assert r.status_code == 200
    assert b'Backup automat' in r.data        # cardul nou de status


def test_ruta_snapshot_db(authenticated_client, app):
    from services import backup
    with app.app_context():
        bdir = backup.dir_backups()
        inainte = {b['nume'] for b in backup.lista_backups()}
    r = authenticated_client.post('/setari/backup/snapshot-db', follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        noi = [b for b in backup.lista_backups()
               if b['nume'] not in inainte and b['nume'].startswith('workforce_manual_')]
    for b in noi:
        try:
            os.remove(os.path.join(bdir, b['nume']))
        except OSError:
            pass
    assert len(noi) >= 1


def test_diagnostics_ops(authenticated_client):
    r = authenticated_client.get('/bim/diagnostics')
    assert r.status_code == 200
    assert b'Sistem' in r.data and b'Versiune Alembic' in r.data
