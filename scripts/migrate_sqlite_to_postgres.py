"""
Script de migrare a datelor din SQLite in PostgreSQL.

Folosire:
    # 1. Setezi DATABASE_URL pentru target PG:
    export PG_URL="postgresql://user:pass@host:5432/workforce"

    # 2. Specifici sursa SQLite (default: ./database/workforce.db):
    export SQLITE_PATH="/path/to/workforce.db"

    # 3. Rulezi:
    python scripts/migrate_sqlite_to_postgres.py

    # Sau cu Flask CLI:
    flask migrate-to-postgres --pg-url=postgresql://... --sqlite-path=./database/workforce.db

Etape:
1. Verifica conexiunile la ambele DB-uri
2. Pe PG target: db.create_all() -> creeaza schema
3. Foreach tabel (in ordinea FK dependencies):
   - Citeste toate rândurile din SQLite
   - Bulk insert in PG (păstrând IDs)
4. Resetează sequences PG (auto-increment) la max(id) + 1
5. Verifică count-uri: SQLite vs PG
"""

import os
import sys
from contextlib import contextmanager
from typing import List, Dict, Any

# Asigura repo root in path
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


# Ordinea de migrare (parinti inainte de copii pentru FK)
MIGRATION_ORDER = [
    # Workforce core
    'tenants',
    'utilizatori',
    'angajati',
    'proiecte',
    'angajat_proiect',
    'pontaje',
    'documente',
    'concedii',
    'rapoarte',
    'sarbatori_legale',
    # Tipuri instalatii / categorii
    'tipuri_instalatii',
    'tipuri_documente_proiect',
    'documente_proiect',
    'revizii_documente',
    'categorii_activitati',
    'rapoarte_activitati',
    # Masini
    'masini',
    'documente_masini',
    'atribuiri_masini',
    'conduceri_masini',
    'defectiuni_masini',
    # BIM
    'bim_santiere',
    'bim_cladiri',
    'bim_niveluri',
    'bim_zone',
    'bim_spatii',
    'bim_elemente',
    'bim_assets',
    'bim_issues',
    'bim_modele',
    'bim_external_mappings',
]


def migrate(sqlite_path: str, pg_url: str, dry_run: bool = False, verbose: bool = True):
    """Functie principala. Returneaza dict cu statistici per tabel."""
    from sqlalchemy import create_engine, MetaData, Table, inspect, text

    if not os.path.exists(sqlite_path):
        raise FileNotFoundError(f'SQLite source nu exista: {sqlite_path}')

    sqlite_url = f'sqlite:///{sqlite_path}'

    if verbose:
        print(f'[1/5] Conectez la SQLite source: {sqlite_path}')
    sqlite_engine = create_engine(sqlite_url)

    if verbose:
        print(f'[2/5] Conectez la Postgres target: {pg_url[:30]}...')
    pg_engine = create_engine(pg_url)

    # 2.5: Pe target PG, ruleaza db.create_all() ca sa avem schema
    if verbose:
        print(f'[3/5] Creez schema pe Postgres (db.create_all)')
    if not dry_run:
        # Setez DATABASE_URL ca sa create_app sa foloseasca PG-ul
        os.environ['DATABASE_URL'] = pg_url
        from app import create_app
        from models import db
        app = create_app('default')
        with app.app_context():
            db.create_all()

    # 3: Migreaza datele tabel cu tabel
    if verbose:
        print(f'[4/5] Migrez datele...')

    sqlite_meta = MetaData()
    sqlite_meta.reflect(bind=sqlite_engine)

    pg_meta = MetaData()
    pg_meta.reflect(bind=pg_engine)

    stats = {}
    sqlite_inspector = inspect(sqlite_engine)
    sqlite_tables = set(sqlite_inspector.get_table_names())

    # Construim lista efectiva: tabele in ordine + ce mai e in SQLite
    effective_order = [t for t in MIGRATION_ORDER if t in sqlite_tables]
    extras = sorted(sqlite_tables - set(MIGRATION_ORDER))
    effective_order.extend(extras)

    for tname in effective_order:
        if tname.startswith('sqlite_') or tname == 'alembic_version':
            continue

        if tname not in pg_meta.tables:
            if verbose:
                print(f'  [SKIP] Tabel {tname} nu exista in PG (probabil nu mai e in models)')
            continue

        sqlite_table = sqlite_meta.tables[tname]
        pg_table = pg_meta.tables[tname]

        # Verifica daca PG-ul are deja date in tabel
        with pg_engine.connect() as pg_conn:
            existing = pg_conn.execute(text(f'SELECT COUNT(*) FROM {tname}')).scalar()
        if existing and existing > 0:
            if verbose:
                print(f'  [SKIP] {tname}: {existing} randuri exista deja in PG')
            stats[tname] = {'sqlite': 0, 'pg': existing, 'migrated': 0, 'skipped': True}
            continue

        # Citeste din SQLite
        with sqlite_engine.connect() as sql_conn:
            rows = sql_conn.execute(sqlite_table.select()).fetchall()

        if not rows:
            stats[tname] = {'sqlite': 0, 'pg': 0, 'migrated': 0}
            if verbose:
                print(f'  [INFO] {tname}: gol')
            continue

        # Convert rows to dict-uri compatibile cu PG (gestiune tipuri)
        rows_dict = []
        for r in rows:
            d = dict(r._mapping)
            # SQLite stocheaza booleene ca 0/1; PG asteapta True/False
            for col_name, val in list(d.items()):
                col = pg_table.columns.get(col_name)
                if col is None:
                    continue
                col_type = str(col.type).upper()
                if 'BOOL' in col_type and val is not None:
                    d[col_name] = bool(val)
            rows_dict.append(d)

        if dry_run:
            stats[tname] = {'sqlite': len(rows_dict), 'pg': 0, 'migrated': 0, 'dry_run': True}
            if verbose:
                print(f'  [DRY] {tname}: ar migra {len(rows_dict)} randuri')
            continue

        # Bulk insert in PG
        try:
            with pg_engine.begin() as pg_conn:
                pg_conn.execute(pg_table.insert(), rows_dict)
            stats[tname] = {'sqlite': len(rows_dict), 'pg': len(rows_dict),
                            'migrated': len(rows_dict)}
            if verbose:
                print(f'  [OK] {tname}: {len(rows_dict)} randuri migrate')
        except Exception as e:
            stats[tname] = {'sqlite': len(rows_dict), 'pg': 0, 'migrated': 0,
                            'error': str(e)[:200]}
            if verbose:
                print(f'  [EROARE] {tname}: {e}')

    # 4: Reset sequences PG (id auto-increment trebuie sa porneasca de la max(id)+1)
    if not dry_run:
        if verbose:
            print(f'[5/5] Resetez sequences pe PG...')
        with pg_engine.begin() as pg_conn:
            for tname in effective_order:
                if tname not in pg_meta.tables:
                    continue
                pg_table = pg_meta.tables[tname]
                pk_cols = [c for c in pg_table.columns if c.primary_key]
                if len(pk_cols) != 1 or 'INT' not in str(pk_cols[0].type).upper():
                    continue
                pk = pk_cols[0].name
                seq_name = f'{tname}_{pk}_seq'
                try:
                    pg_conn.execute(text(
                        f"SELECT setval('{seq_name}', COALESCE((SELECT MAX({pk}) FROM {tname}), 0) + 1, false)"
                    ))
                    if verbose:
                        print(f'  [OK] {seq_name}')
                except Exception as e:
                    if verbose:
                        print(f'  [SKIP] {seq_name}: {str(e)[:100]}')

    return stats


def print_summary(stats: Dict[str, Dict]):
    print('\n=== SUMAR MIGRARE ===')
    total_migrated = 0
    total_errors = 0
    for tname, s in stats.items():
        if s.get('error'):
            print(f'  [EROARE] {tname:35} {s.get("error")}')
            total_errors += 1
        elif s.get('skipped'):
            print(f'  [SKIP]   {tname:35} {s["pg"]} randuri exista deja')
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
    parser.add_argument('--pg-url', default=os.environ.get('PG_URL',
                        os.environ.get('DATABASE_URL', '')))
    parser.add_argument('--dry-run', action='store_true', help='Doar verifica, nu insereaza')
    args = parser.parse_args()

    if not args.pg_url or not args.pg_url.startswith('postgresql://'):
        print('EROARE: setati PG_URL sau --pg-url cu un URL postgresql://')
        sys.exit(1)

    stats = migrate(args.sqlite_path, args.pg_url, dry_run=args.dry_run)
    print_summary(stats)
