"""0035 situatie_retentii_manual

Revision ID: 0035_situatie_retentii_manual
Revises: 0034_situatii_retentii
Create Date: 2026-06-22 00:00:00.000000

Marcaj explicit de editare manuala a retentiei/garantiei pe situatiile lunare,
fix de corectitudine la Deviz Faza 3.

Problema: discriminatorul de 'editare manuala' din _aplica_retentii_garantii era
dedus din 'sumele sunt non-NULL'. Prima auto-generare cu flag ON populeaza
sumele -> orice regenerare ulterioara le ingheta in loc sa le recalculeze din
valoare_luna * procent. Coloana noua retentii_editate_manual e setata DOAR de
ruta situatie_retentii, deci distinge corect auto-populate de editare reala.

Strict aditiv: o singura coloana noua nullable pe 'situatii_lunare'.
  - situatii_lunare.retentii_editate_manual (BOOLEAN, default False, nullable)

Pe prod se aplica prin ALTER idempotent (CLI migrate-bim, in link_targets cu
verificare 'col in cols') + alembic stamp head (NU alembic upgrade - alembic e
desincronizat de schema reala pe prod).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0035_situatie_retentii_manual'
down_revision: Union[str, Sequence[str], None] = '0034_situatii_retentii'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('situatii_lunare', schema=None) as batch_op:
        batch_op.add_column(sa.Column('retentii_editate_manual', sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('situatii_lunare', schema=None) as batch_op:
        batch_op.drop_column('retentii_editate_manual')
