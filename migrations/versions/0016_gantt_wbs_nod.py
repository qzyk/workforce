"""0016 gantt_wbs_nod

Revision ID: 0016_gantt_wbs_nod
Revises: 0015_consum_utilaj
Create Date: 2026-06-03 00:00:00.000000

Editor WBS: arbore editabil per plan salvat (redenumire/reordonare/regrupare).
Tabel NOU (strict aditiv) - pe prod se aplica prin db.create_all() + alembic
stamp head (NU alembic upgrade, NU ALTER pe tabele existente).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0016_gantt_wbs_nod'
down_revision: Union[str, Sequence[str], None] = '0015_consum_utilaj'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'gantt_wbs_nod',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('parinte_id', sa.Integer(), nullable=True),
        sa.Column('tip', sa.String(length=20), nullable=False),
        sa.Column('nume', sa.String(length=300), nullable=False),
        sa.Column('ordine', sa.Integer(), nullable=False),
        sa.Column('activitate_ref', sa.String(length=20), nullable=True),
        sa.Column('data_creare', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.ForeignKeyConstraint(['plan_id'], ['gantt_plan.id'], ),
        sa.ForeignKeyConstraint(['parinte_id'], ['gantt_wbs_nod.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('gantt_wbs_nod', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_gantt_wbs_nod_tenant_id'),
                              ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_gantt_wbs_nod_plan_id'),
                              ['plan_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_gantt_wbs_nod_parinte_id'),
                              ['parinte_id'], unique=False)


def downgrade() -> None:
    op.drop_table('gantt_wbs_nod')
