"""0023 clash spatial + dedup

Revision ID: 0023_clash_spatial_dedup
Revises: 0022_bim_elemente_bbox
Create Date: 2026-06-15 00:00:00.000000

Faza 3 BIM: clash detection scalabil + deduplicare intre rulari.
- ADD COLUMN bim_clash_runs.tolerance_mm (INTEGER, NULLABLE) - toleranta de
  intersectie AABB in mm; NULL -> fallback la 1mm istoric (rezultat neschimbat).
- CREATE TABLE bim_clash_group - grup persistent de clash deduplicat intre rulari
  (pereche element_a < element_b + tip, status pus de utilizator, run_ids).
Strict aditiv - pe prod se aplica prin migrate-bim (ALTER idempotent +
db.create_all pentru tabela noua), NU prin alembic upgrade.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0023_clash_spatial_dedup'
down_revision: Union[str, Sequence[str], None] = '0022_bim_elemente_bbox'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Coloana noua pe tabela existenta
    with op.batch_alter_table('bim_clash_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tolerance_mm', sa.Integer(), nullable=True))

    # 2. Tabela noua de deduplicare intre rulari
    op.create_table(
        'bim_clash_group',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('element_a_id', sa.Integer(), nullable=False),
        sa.Column('element_b_id', sa.Integer(), nullable=False),
        sa.Column('tip', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('severitate', sa.String(length=20), nullable=False),
        sa.Column('prima_detectie', sa.DateTime(), nullable=False),
        sa.Column('ultima_detectie', sa.DateTime(), nullable=False),
        sa.Column('run_ids_json', sa.Text(), nullable=True),
        sa.Column('issue_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['element_a_id'], ['bim_elemente.id']),
        sa.ForeignKeyConstraint(['element_b_id'], ['bim_elemente.id']),
        sa.ForeignKeyConstraint(['issue_id'], ['bim_issues.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'element_a_id', 'element_b_id', 'tip',
                            name='uq_clash_group_pereche'),
    )
    with op.batch_alter_table('bim_clash_group', schema=None) as batch_op:
        batch_op.create_index('ix_bim_clash_group_tenant_id', ['tenant_id'])
        batch_op.create_index('ix_bim_clash_group_element_a_id', ['element_a_id'])
        batch_op.create_index('ix_bim_clash_group_element_b_id', ['element_b_id'])
        batch_op.create_index('ix_bim_clash_group_tip', ['tip'])
        batch_op.create_index('ix_bim_clash_group_status', ['status'])
        batch_op.create_index('ix_bim_clash_group_ultima_detectie', ['ultima_detectie'])
        batch_op.create_index('ix_clash_group_status', ['status'])


def downgrade() -> None:
    with op.batch_alter_table('bim_clash_group', schema=None) as batch_op:
        batch_op.drop_index('ix_clash_group_status')
        batch_op.drop_index('ix_bim_clash_group_ultima_detectie')
        batch_op.drop_index('ix_bim_clash_group_status')
        batch_op.drop_index('ix_bim_clash_group_tip')
        batch_op.drop_index('ix_bim_clash_group_element_b_id')
        batch_op.drop_index('ix_bim_clash_group_element_a_id')
        batch_op.drop_index('ix_bim_clash_group_tenant_id')
    op.drop_table('bim_clash_group')

    with op.batch_alter_table('bim_clash_runs', schema=None) as batch_op:
        batch_op.drop_column('tolerance_mm')
