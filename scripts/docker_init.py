"""
Init pentru containerul Docker (instanta-per-client): pregateste schema DB +
seed minim, idempotent. Ruleaza din entrypoint INAINTE de gunicorn.

Logica schema:
  - DB nou (fara tabela alembic_version)  -> db.create_all() + `alembic stamp head`
    (schema completa instant, marcata ca up-to-date, fara replay de migratii).
  - DB existent                            -> `alembic upgrade head` + db.create_all()
    (aplica migratiile lipsa; create_all prinde orice tabel nou neacoperit inca).

Seed (din variabile de mediu, totul idempotent):
  - ADMIN_EMAIL / ADMIN_PASSWORD          -> creeaza un admin daca nu exista.
  - FEATURE_FLAGS (lista separata prin ,) -> activeaza modulele cumparate.

Nu arunca daca seed-ul lipseste; doar logheaza si continua.
"""

import os
import sys

# Repo root in sys.path (rulam din /app in container, dar fim defensivi)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _alembic_cfg():
    from alembic.config import Config
    return Config(os.path.join(_ROOT, 'alembic.ini'))


def prepare_schema(db):
    from sqlalchemy import inspect
    from alembic import command

    insp = inspect(db.engine)
    tables = set(insp.get_table_names())
    cfg = _alembic_cfg()

    if 'alembic_version' not in tables:
        db.create_all()
        command.stamp(cfg, 'head')
        print('[init] DB nou: create_all + alembic stamp head', flush=True)
    else:
        command.upgrade(cfg, 'head')
        db.create_all()
        print('[init] DB existent: alembic upgrade head + create_all', flush=True)


def seed_admin(db):
    from models import Utilizator
    email = (os.environ.get('ADMIN_EMAIL') or '').strip()
    password = os.environ.get('ADMIN_PASSWORD') or ''
    if not email or not password:
        print('[init] ADMIN_EMAIL/ADMIN_PASSWORD nesetate - skip seed admin', flush=True)
        return
    if Utilizator.query.filter_by(email=email).first():
        print(f'[init] admin {email} exista deja - skip', flush=True)
        return
    u = Utilizator(
        nume=os.environ.get('ADMIN_NUME', 'Admin'),
        prenume=os.environ.get('ADMIN_PRENUME', 'Edifico'),
        email=email, rol='admin', activ=True,
    )
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    print(f'[init] admin {email} creat', flush=True)


def seed_flags(db):
    from services.feature_flags import set_flag
    raw = (os.environ.get('FEATURE_FLAGS') or '').strip()
    if not raw:
        print('[init] FEATURE_FLAGS gol - niciun modul activat explicit', flush=True)
        return
    for key in [f.strip() for f in raw.split(',') if f.strip()]:
        set_flag(key, True, commit=True)
        print(f'[init] modul ON: {key}', flush=True)


def main():
    from app import create_app
    from models import db
    app = create_app('default')
    with app.app_context():
        prepare_schema(db)
        seed_admin(db)
        seed_flags(db)
    print('[init] gata.', flush=True)
    # iesim explicit (eventualele thread-uri APScheduler sunt daemon)
    os._exit(0)


if __name__ == '__main__':
    main()
