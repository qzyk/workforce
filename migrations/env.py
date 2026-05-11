"""
Alembic environment pentru EDIFICO WORKFORCE.

- URL-ul DB se preia automat din config.Config.SQLALCHEMY_DATABASE_URI
  (care respecta DATABASE_URL env var). Nu trebuie editat manual in alembic.ini.
- target_metadata = db.metadata din models.py, deci 'alembic revision --autogenerate'
  detecteaza automat schimbarile in modele.
- Suporta SQLite (cu render_as_batch pentru ALTER TABLE) si MySQL.
"""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Asigura ca repo root (parent dir) e in sys.path ca sa putem importa config + models
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

# Importam dupa ce am ajustat sys.path
from config import Config  # noqa: E402
from models import db  # noqa: E402

# Inregistram TOATE modelele in metadata (Flask-SQLAlchemy le inregistreaza
# la import-ul claselor). Importul de mai sus aduce in scope tot fisierul models.
import models  # noqa: F401, E402

# Alembic Config object
config = context.config

# Suprascriem URL-ul cu cel din config.py (care vede DATABASE_URL)
config.set_main_option('sqlalchemy.url', Config.SQLALCHEMY_DATABASE_URI)

# Logger setup
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata target pentru autogenerate
target_metadata = db.metadata


def _is_sqlite_url(url: str) -> bool:
    return url.startswith('sqlite:')


def run_migrations_offline() -> None:
    """Migratii in offline mode (genereaza SQL fara conexiune)."""
    url = config.get_main_option('sqlalchemy.url')
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
        # batch mode pe SQLite pentru ALTER TABLE-uri sigure
        render_as_batch=_is_sqlite_url(url or ''),
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Migratii in online mode (cu conexiune live)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        is_sqlite = connection.dialect.name == 'sqlite'
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=is_sqlite,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
