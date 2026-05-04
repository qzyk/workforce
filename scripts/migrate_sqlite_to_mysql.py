"""
Script de migrare a datelor din SQLite in MySQL.

Folosire:
    # 1. Setezi MYSQL_URL pentru target (PA folosesc <user>$<dbname>):
    export MYSQL_URL='mysql+pymysql://qzyk97:PAROLA@qzyk97.mysql.pythonanywhere-services.com/qzyk97$workforce'

    # 2. Specifici sursa SQLite (default: ./database/workforce.db):
    export SQLITE_PATH="/path/to/workforce.db"

    # 3. Rulezi:
    python scripts/migrate_sqlite_to_mysql.py

    # Sau cu Flask CLI:
    flask migrate-to-mysql --mysql-url='mysql+pymysql://...' --sqlite-path=./database/workforce.db

Etape:
1. Verifica conexiunile la ambele DB-uri
2. Pe MySQL target: db.create_all() -> creeaza schema
3. Foreach tabel (in ordinea FK dependencies):
   - Citeste toate randurile din SQLite
   - Bulk insert in MySQL (pastrand IDs)
4. Setez AUTO_INCREMENT la max(id)+1 pentru fiecare tabel

Atentie pe PythonAnywhere:
- Numele DB e prefixat: <username>$<dbname> (ex: qzyk97$workforce)
- $ trebuie incadrat in ghilimele simple ('...') in shell.
- MySQL pe PA accepta doar conexiuni din serverele PA (firewall pe IP).
"""

import os
import sys
from typing import Dict

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


MIGRATION_ORDER = [
    'tenants', 'utilizatori', 'angajati', 'proiecte', 'angajat_proiect',
    'pontaje', 'documente', 'concedii', 'rapoarte', 'sarbatori_legale',
    'tipuri_instalatii', 'tipuri_documente_proiect', 'documente_proiect',
    'revizii_documente', 'categorii_activitati', 'rapoarte_activitati',
    'masini', 'documente_masini', 'atribuiri_masini', 'conduceri_masini',
    'defectiuni_masini',
    'bim_santiere', 'bim_cladiri', 'bim_niveluri', 'bim_zone', 'bim_spatii',
    'bim_elemente', 'bim_assets', 'bim_issues', 'bim_modele',
    'bim_external_mappings',
]


def migrate(sqlite_path, mysql_url, dry_run=False, verbose=True):
    from sqlalchemy import create_engine, MetaData, inspect, text

    if not os.path.exists(sqlite_path):
        raise FileNotFoundError(f'SQLite source nu exista: {sqlite_path}')

    sqlite_url = f'sqlite:///{sqlite_path}'

    if verbose:
        print(f'[1/4] Conectez la SQLite source: {sqlite_path}')
    sqlite_engine = create_engine(sqlite_url)

    if verbose:
        safe_url = mysql_url
        if '@' in safe_url:
            try:
                pre, post = safe_url.split('@', 1)
                if ':' in pre.split('//')[-1]:
                    user = pre.split('//')[-1].split(':')[0]
                    safe_url = f'mysql+pymysql://{user}:***@{post}'
            except Exception:
                pass
        print(f'[2/4] Conectez la MySQL target: {safe_url}')
    mysql_engine = create_engine(mysql_url)

    if verbose:
        print(f'[3/4] Creez schema pe MySQL (db.create_all)')
    if not dry_run:
        os.environ['DATABASE_URL'] = mysql_url
        from app import create_app
        from models import db
        app = create_app('default')
        with app.app_context():
            db.create_all()

    if verbose:
        print(f'[4/4] Migrez datele...')

    sqlite_meta = MetaData()
    sqlite_meta.reflect(bind=sqlite_engine)

    mysql_meta = MetaData()
    mysql_meta.reflect(bind=mysql_engine)

    stats = {}
    sqlite_tables = set(inspect(sqlite_engine).get_table_names())

    effective_order = [t for t in MIGRATION_ORDER if t in sqlite_tables]
    extras = sorted(sqlite_tables - set(MIGRATION_ORDER))
    effective_order.extend(extras)

    for tname in effective_order:
        if tname.startswith('sqlite_') or tname == 'alembic_version':
            continue
        if tname not in mysql_meta.tables:
            if verbose:
                print(f'  [SKIP] Tabel {tname} nu exista in MySQL')
            continue

        sqlite_table = sqlite_meta.tables[tname]
        mysql_table = mysql_meta.tables[tname]

        with mysql_engine.connect() as my_conn:
            existing = my_conn.execute(text(f'SELECT COUNT(*) FROM {tname}')).scalar()
        if existing and existing > 0:
            if verbose:
                print(f'  [SKIP] {tname}: {existing} randuri exista deja in MySQL')
            stats[tname] = {'sqlite': 0, 'mysql': existing, 'migrated': 0, 'skipped': True}
            continue

        with sqlite_engine.connect() as sql_conn:
            rows = sql_conn.execute(sqlite_table.select()).fetchall()

        if not rows:
            stats[tname] = {'sqlite': 0, 'mysql': 0, 'migrated': 0}
            if verbose:
                print(f'  [INFO] {tname}: gol')
            continue

        rows_dict = []
        for r in rows:
            d = dict(r._mapping)
            for col_name, val in list(d.items()):
                col = mysql_table.columns.get(col_name)
                if col is None:
                    continue
                col_type = str(col.type).upper()
                if 'BOOL' in col_type and val is not None:
                    d[col_name] = bool(val)
            rows_dict.append(d)

        if dry_run:
            stats[tname] = {'sqlite': len(rows_dict), 'mysql': 0, 'migrated': 0, 'dry_run': True}
            if verbose:
                print(f'  [DRY] {tname}: ar migra {len(rows_dict)} randuri')
            continue

        try:
            with mysql_engine.begin() as my_conn:
                my_conn.execute(text('SET FOREIGN_KEY_CHECKS=0'))
                my_conn.execute(mysql_table.insert(), rows_dict)
                my_conn.execute(text('SET FOREIGN_KEY_CHECKS=1'))
            stats[tname] = {'sqlite': len(rows_dict), 'mysql': len(rows_dict),
                            'migrated': len(rows_dict)}
            if verbose:
                print(f'  [OK] {tname}: {len(rows_dict)} randuri migrate')
        except Exception as e:
            stats[tname] = {'sqlite': len(rows_dict), 'mysql': 0, 'migrated': 0,
                            'error': str(e)[:200]}
            if verbose:
                print(f'  [EROARE] {tname}: {e}')

    if not dry_run:
        if verbose:
            print(f'\n[OK] Setez AUTO_INCREMENT...')
        with mysql_engine.begin() as my_conn:
            for tname in effective_order:
                if tname not in mysql_meta.tables:
                    continue
                mysql_table = mysql_meta.tables[tname]
                pk_cols = [c for c in mysql_table.columns if c.primary_key]
                if len(pk_cols) != 1 or 'INT' not in str(pk_cols[0].type).upper():
                    continue
                pk = pk_cols[0].name
                try:
                    max_id = my_conn.execute(text(f'SELECT MAX({pk}) FROM {tname}')).scalar() or 0
                    my_conn.execute(text(f'ALTER TABLE {tname} AUTO_INCREMENT = {max_id + 1}'))
                except Exception as e:
                    if verbose:
                        print(f'  [SKIP] AUTO_INCREMENT {tname}: {str(e)[:80]}')

    return stats


def print_summary(stats):
    print('\n=== SUMAR MIGRARE ===')
    total_migrated = 0
    total_errors = 0
    for tname, s in stats.items():
        if s.get('error'):
            print(f'  [EROARE] {tname:35} {s.get("error")}')
            total_errors += 1
        elif s.get('skipped'):
            print(f'  [SKIP]   {tname:35} {s["mysql"]} randuri exista deja')
        elif s.get('dry_run'):
            print(f'  [DRY]    {tname:35} {s["sqlite"]} randuri ar fi migrate')
        else:
            total_migrated += s['migrated']
            print(f'  [OK]     {tname:35} {s["migrated"]:>6} randuri')
    print(f'\nTotal randuri migrate: {total_migrated}')
    if total_errors:
        print(f'Erori: {total_errors}')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--sqlite-path', default=os.environ.get('SQLITE_PATH',
                        os.path.join(_repo_root, 'database', 'workforce.db')))
    parser.add_argument('--mysql-url', default=os.environ.get('MYSQL_URL',
                        os.environ.get('DATABASE_URL', '')))
    parser.add_argument('--dry-run', action='store_true', help='Doar verifica, nu insereaza')
    args = parser.parse_args()

    if not args.mysql_url or 'mysql' not in args.mysql_url:
        print('EROARE: setati MYSQL_URL sau --mysql-url cu un URL mysql+pymysql://')
        sys.exit(1)

    stats = migrate(args.sqlite_path, args.mysql_url, dry_run=args.dry_run)
    print_summary(stats)
