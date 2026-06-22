"""0034 situatii_retentii

Revision ID: 0034_situatii_retentii
Revises: 0033_competente
Create Date: 2026-06-22 00:00:00.000000

Retentii + garantii de buna executie pe situatiile lunare, Deviz Faza 3.

Strict aditiv: NUMAI coloane noi nullable pe doua tabele existente.
  - situatii_lunare: retentie_procent, retentie_suma, garantie_bex_suma,
                     avans_recuperat, plata_neta
  - contracte:       retentie_procent_default, garantie_bex_procent

Toate nullable; populate doar cu flag 'situatii-retentii' ON. Cu OFF raman NULL
si situatia ramane identica cu cea istorica (zero regresie).

Pe prod se aplica prin ALTER idempotent (CLI migrate-bim, 7 coloane in
link_targets cu verificare 'col in cols') + alembic stamp head (NU alembic
upgrade - alembic e desincronizat de schema reala pe prod).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0034_situatii_retentii'
down_revision: Union[str, Sequence[str], None] = '0033_competente'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) coloane noi NULLABLE pe 'situatii_lunare'
    with op.batch_alter_table('situatii_lunare', schema=None) as batch_op:
        batch_op.add_column(sa.Column('retentie_procent', sa.Numeric(precision=5, scale=2), nullable=True))
        batch_op.add_column(sa.Column('retentie_suma', sa.Numeric(precision=14, scale=2), nullable=True))
        batch_op.add_column(sa.Column('garantie_bex_suma', sa.Numeric(precision=14, scale=2), nullable=True))
        batch_op.add_column(sa.Column('avans_recuperat', sa.Numeric(precision=14, scale=2), nullable=True))
        batch_op.add_column(sa.Column('plata_neta', sa.Numeric(precision=14, scale=2), nullable=True))

    # 2) coloane noi NULLABLE pe 'contracte' (valori implicite contractuale)
    with op.batch_alter_table('contracte', schema=None) as batch_op:
        batch_op.add_column(sa.Column('retentie_procent_default', sa.Numeric(precision=5, scale=2), nullable=True))
        batch_op.add_column(sa.Column('garantie_bex_procent', sa.Numeric(precision=5, scale=2), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('contracte', schema=None) as batch_op:
        batch_op.drop_column('garantie_bex_procent')
        batch_op.drop_column('retentie_procent_default')

    with op.batch_alter_table('situatii_lunare', schema=None) as batch_op:
        batch_op.drop_column('plata_neta')
        batch_op.drop_column('avans_recuperat')
        batch_op.drop_column('garantie_bex_suma')
        batch_op.drop_column('retentie_suma')
        batch_op.drop_column('retentie_procent')
