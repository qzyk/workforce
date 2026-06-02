"""
Backup automat al bazei de date (self-hosted, fara SaaS — datele stau pe disk-ul tau).

SQLite (prod-ul actual): copie CONSISTENTA prin API-ul sqlite3 `.backup()`
(sigura chiar daca aplicatia scrie in acel moment), nu un simplu `cp`.
MySQL: indrumare spre `scripts/backup_before_alembic.sh` (mysqldump).

Folosit din 3 locuri:
  - job APScheduler zilnic (services/notificari_job.init_scheduler)
  - comanda CLI `flask backup`
  - buton manual in /setari/backup (admin)

Rotatie: pastreaza ultimele N backup-uri 'auto'; cele manuale nu se sterg.
"""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
from datetime import datetime

from flask import current_app


def cale_db() -> str | None:
    """Calea absoluta a fisierului SQLite, sau None daca DB nu e SQLite."""
    uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '') or ''
    if uri.startswith('sqlite:///'):
        return uri[len('sqlite:///'):]
    return None


def dir_backups() -> str:
    """Directorul de backup-uri (creat daca lipseste)."""
    d = os.path.join(current_app.root_path, 'backups')
    os.makedirs(d, exist_ok=True)
    return d


def creeaza_backup(eticheta: str = 'auto') -> dict:
    """Creeaza un backup .db al bazei SQLite.

    Returneaza {ok, nume, path, size, mesaj}. Graceful pe MySQL / DB lipsa."""
    src = cale_db()
    if not src:
        return {'ok': False,
                'mesaj': 'DB nu e SQLite (MySQL: foloseste mysqldump / '
                         'scripts/backup_before_alembic.sh).'}
    if not os.path.exists(src):
        return {'ok': False, 'mesaj': f'Fisierul DB nu exista: {src}'}

    eticheta = re.sub(r'[^A-Za-z0-9_-]', '', eticheta) or 'auto'
    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    nume = f'workforce_{eticheta}_{ts}.db'
    dst = os.path.join(dir_backups(), nume)

    try:
        con = sqlite3.connect(src)
        bck = sqlite3.connect(dst)
        try:
            with bck:
                con.backup(bck)          # copie consistenta, chiar in timpul scrierii
        finally:
            bck.close()
            con.close()
    except Exception:
        shutil.copy2(src, dst)           # fallback: copie simpla a fisierului

    return {'ok': True, 'nume': nume, 'path': dst,
            'size': os.path.getsize(dst), 'mesaj': 'Backup creat.'}


def lista_backups() -> list:
    """[{nume, size, mtime, auto}] sortat descrescator dupa data."""
    d = dir_backups()
    out = []
    for f in os.listdir(d):
        if not (f.endswith('.db') or f.endswith('.sql')):
            continue
        p = os.path.join(d, f)
        try:
            st = os.stat(p)
        except OSError:
            continue
        out.append({'nume': f, 'size': st.st_size, 'mtime': st.st_mtime,
                    'auto': f.startswith('workforce_auto_')})
    return sorted(out, key=lambda x: x['mtime'], reverse=True)


def roteste(maxim: int = 14, prefix: str = 'workforce_auto_') -> int:
    """Pastreaza ultimele `maxim` backup-uri automate; sterge restul.

    Backup-urile manuale (alt prefix) NU se ating. Returneaza nr. sterse."""
    d = dir_backups()
    autos = sorted(f for f in os.listdir(d)
                   if f.startswith(prefix) and f.endswith('.db'))
    de_sters = autos[:-maxim] if maxim > 0 and len(autos) > maxim else []
    n = 0
    for f in de_sters:
        try:
            os.remove(os.path.join(d, f))
            n += 1
        except OSError:
            pass
    return n


def ruleaza_backup_automat(maxim: int = 14) -> dict:
    """Job zilnic: creeaza backup 'auto' + roteste. Returneaza statisticile."""
    r = creeaza_backup('auto')
    r['rotite_sterse'] = roteste(maxim) if r.get('ok') else 0
    return r


def status() -> dict:
    """Sumar pentru pagina de diagnostics: nr, total marime, ultimul backup."""
    bks = lista_backups()
    total = sum(b['size'] for b in bks)
    ultim = bks[0] if bks else None
    return {
        'nr': len(bks),
        'total_size': total,
        'ultim_nume': ultim['nume'] if ultim else None,
        'ultim_mtime': ultim['mtime'] if ultim else None,
        'sqlite': cale_db() is not None,
    }
