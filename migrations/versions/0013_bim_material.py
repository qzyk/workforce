"""0013 bim element material (pentru auto-pricing din IFC)

Revision ID: 0013_bim_material
Revises: 0011_deviz_pricing
Create Date: 2026-05-26 10:00:00.000000

Adauga bim_elemente.material (ex. Beton C25/30, S355, BST500s) extras la
importul IFC, folosit la potrivirea cu catalogul de preturi 2026.

NB: pe alt branch exista 0012_conducere_consum (tot copil al 0011). La merge-ul
in main se reconciliaza arborele de migratii (merge revision).
Strict aditiv, coloana nullable.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0013_bim_material'
down_revision: Union[str, Sequence[str], None] = '0011_deviz_pricing'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('bim_elemente', schema=None) as batch_op:
        batch_op.add_column(sa.Column('material', sa.String(length=120), nullable=True))
        batch_op.create_index(batch_op.f('ix_bim_elemente_material'), ['material'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('bim_elemente', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_bim_elemente_material'))
        batch_op.drop_column('material')
