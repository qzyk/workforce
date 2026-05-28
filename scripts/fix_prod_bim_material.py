"""
Script idempotent PROD: adauga coloana bim_elemente.material (auto-pricing IFC).
create_all() NU adauga coloane pe tabele existente -> ALTER necesar pe prod.

Rulare pe PA:
    cd ~/workforce
    ~/.virtualenvs/workforce-env/bin/python scripts/fix_prod_bim_material.py
Apoi: Web -> Reload. Idempotent (sare daca exista deja).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text  # noqa: E402
from app import create_app  # noqa: E402
from models import db  # noqa: E402

TABEL = 'bim_elemente'
COLOANE = {'material': 'VARCHAR(120)'}


def main():
    app = create_app('default')
    with app.app_context():
        insp = inspect(db.engine)
        if TABEL not in insp.get_table_names():
            print(f'[!] {TABEL} nu exista - rulez create_all().')
            db.create_all()
            return
        existente = {c['name'] for c in insp.get_columns(TABEL)}
        adaugate = 0
        for col, definitie in COLOANE.items():
            if col in existente:
                print(f'[=] {TABEL}.{col} exista deja - skip.')
                continue
            with db.engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE {TABEL} ADD COLUMN {col} {definitie}'))
            print(f'[+] ALTER TABLE {TABEL} ADD COLUMN {col} {definitie}')
            adaugate += 1
        db.create_all()
        print(f'\nGata. Coloane adaugate: {adaugate}. Acum: Web -> Reload.')


if __name__ == '__main__':
    main()
