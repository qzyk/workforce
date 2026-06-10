"""0019 merge banca_preturi + obiectiv_obiect

Revision ID: 0019_merge_banca_obiectiv
Revises: 0018_banca_preturi, 0018_obiectiv_obiect
Create Date: 2026-06-10 12:00:00.000000

Migratie de MERGE (fara DDL): uneste cele doua ramuri paralele de migratii
(banca de preturi si ierarhia obiectiv) intr-un singur head. Pe prod:
db.create_all() + alembic stamp head (NU alembic upgrade).
"""
from typing import Sequence, Union


revision: str = '0019_merge_banca_obiectiv'
down_revision: Union[str, Sequence[str], None] = ('0018_banca_preturi',
                                                  '0018_obiectiv_obiect')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
