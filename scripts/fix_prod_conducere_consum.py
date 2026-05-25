"""
Script idempotent pentru PROD (PythonAnywhere) - adauga coloanele necesare
calculatorului de consum pe tabela existenta `conduceri_masini`.

De ce: `db.create_all()` NU adauga coloane pe tabele care exista deja.
Pe un DB cu date (prod), coloanele noi trebuie adaugate cu ALTER TABLE.

Rulare pe PA (in venv):
    cd ~/workforce
    ~/.virtualenvs/workforce-env/bin/python scripts/fix_prod_conducere_consum.py

Apoi: Web -> Reload. Ruleaza de cate ori vrei (sare peste coloanele existente).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text  # noqa: E402

from app import create_app  # noqa: E402
from models import db  # noqa: E402

# coloana -> definitie SQL (compatibil SQLite + MySQL)
COLOANE_NOI = {
    'distanta_km': 'NUMERIC(7, 2)',
    'combustibil_consumat': 'NUMERIC(7, 2)',
    'waypoints_json': 'TEXT',
}

TABEL = 'conduceri_masini'


def main():
    app = create_app('default')
    with app.app_context():
        insp = inspect(db.engine)
        if TABEL not in insp.get_table_names():
            print(f'[!] Tabela {TABEL} nu exista - rulez db.create_all() pentru tabele noi.')
            db.create_all()
            insp = inspect(db.engine)

        existente = {c['name'] for c in insp.get_columns(TABEL)}
        adaugate = 0
        for col, definitie in COLOANE_NOI.items():
            if col in existente:
                print(f'[=] {TABEL}.{col} exista deja - skip.')
                continue
            sql = f'ALTER TABLE {TABEL} ADD COLUMN {col} {definitie}'
            print(f'[+] {sql}')
            with db.engine.begin() as conn:
                conn.execute(text(sql))
            adaugate += 1

        # Pentru orice tabela complet noua (nu e cazul aici, dar e safe)
        db.create_all()
        print(f'\nGata. Coloane adaugate: {adaugate}. Acum: Web -> Reload.')


if __name__ == '__main__':
    main()
