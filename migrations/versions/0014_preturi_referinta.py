"""0014 preturi referinta (catalog auto-pricing BIM 2026)

Revision ID: 0014_preturi_referinta
Revises: 0013_bim_material
Create Date: 2026-05-26 11:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0014_preturi_referinta'
down_revision: Union[str, Sequence[str], None] = '0013_bim_material'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'preturi_referinta',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('categorie_lucrare', sa.String(length=60), nullable=False),
        sa.Column('um', sa.String(length=20), nullable=False),
        sa.Column('pret_unitar', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('material', sa.String(length=120), nullable=True),
        sa.Column('sursa', sa.String(length=120), nullable=True),
        sa.Column('an_referinta', sa.Integer(), nullable=True),
        sa.Column('data_actualizare', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'categorie_lucrare', 'um',
                            name='uix_pret_tenant_cat_um'),
    )
    with op.batch_alter_table('preturi_referinta', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_preturi_referinta_categorie_lucrare'),
                              ['categorie_lucrare'], unique=False)
        batch_op.create_index(batch_op.f('ix_preturi_referinta_tenant_id'),
                              ['tenant_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('preturi_referinta', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_preturi_referinta_tenant_id'))
        batch_op.drop_index(batch_op.f('ix_preturi_referinta_categorie_lucrare'))
    op.drop_table('preturi_referinta')
