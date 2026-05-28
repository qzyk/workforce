"""0015 norme productivitate (auto-planning executie BIM)

Revision ID: 0015_norme_productivitate
Revises: 0014_preturi_referinta
Create Date: 2026-05-26 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0015_norme_productivitate'
down_revision: Union[str, Sequence[str], None] = '0014_preturi_referinta'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'norme_productivitate',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('categorie_lucrare', sa.String(length=60), nullable=False),
        sa.Column('um', sa.String(length=20), nullable=False),
        sa.Column('randament_zi', sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column('echipe_default', sa.Integer(), nullable=True),
        sa.Column('data_actualizare', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'categorie_lucrare', name='uix_norma_tenant_cat'),
    )
    with op.batch_alter_table('norme_productivitate', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_norme_productivitate_categorie_lucrare'),
                              ['categorie_lucrare'], unique=False)
        batch_op.create_index(batch_op.f('ix_norme_productivitate_tenant_id'),
                              ['tenant_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('norme_productivitate', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_norme_productivitate_tenant_id'))
        batch_op.drop_index(batch_op.f('ix_norme_productivitate_categorie_lucrare'))
    op.drop_table('norme_productivitate')
