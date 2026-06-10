"""0020 pret_resursa_categorie

Revision ID: 0020_pret_resursa_categorie
Revises: 0019_merge_banca_obiectiv
Create Date: 2026-06-10 14:00:00.000000

Coloana `categorie` pe pret_resursa (categorie de lucrare, clasificata automat
la import, editabila din UI). Strict aditiv. Pe prod: ALTER TABLE manual +
alembic stamp head (db.create_all NU adauga coloane pe tabele existente).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0020_pret_resursa_categorie'
down_revision: Union[str, Sequence[str], None] = '0019_merge_banca_obiectiv'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('pret_resursa', schema=None) as batch_op:
        batch_op.add_column(sa.Column('categorie', sa.String(length=60), nullable=True))
        batch_op.create_index('ix_pret_resursa_categorie', ['categorie'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('pret_resursa', schema=None) as batch_op:
        batch_op.drop_index('ix_pret_resursa_categorie')
        batch_op.drop_column('categorie')
