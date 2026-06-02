"""0014 proiect_santier

Revision ID: 0014_proiect_santier
Revises: 0013_gantt_plan
Create Date: 2026-06-02 03:00:00.000000

Asociere many-to-many proiecte <-> bim_santiere. Tabel NOU (strict aditiv) - pe
prod se aplica prin db.create_all() + alembic stamp head (nu ALTER pe proiecte).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0014_proiect_santier'
down_revision: Union[str, Sequence[str], None] = '0013_gantt_plan'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'proiect_santier',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('proiect_id', sa.Integer(), nullable=False),
        sa.Column('santier_id', sa.Integer(), nullable=False),
        sa.Column('data_creare', sa.DateTime(), nullable=True),
        sa.Column('creat_de_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['creat_de_id'], ['utilizatori.id'], ),
        sa.ForeignKeyConstraint(['proiect_id'], ['proiecte.id'], ),
        sa.ForeignKeyConstraint(['santier_id'], ['bim_santiere.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('proiect_id', 'santier_id', name='uix_proiect_santier'),
    )
    with op.batch_alter_table('proiect_santier', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_proiect_santier_proiect_id'),
                              ['proiect_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_proiect_santier_santier_id'),
                              ['santier_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_proiect_santier_tenant_id'),
                              ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_table('proiect_santier')
