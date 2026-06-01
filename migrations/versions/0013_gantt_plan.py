"""0013 gantt plan

Revision ID: 0013_gantt_plan
Revises: 0012_gantt_import_db
Create Date: 2026-06-02 10:00:00.000000

Tabel pentru planuri Gantt salvate (legate optional de un proiect). Pastram sursa
(fisierul F3 + maparea) ca sa re-rulam pipeline-ul la deschidere. Strict aditiv.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0013_gantt_plan'
down_revision: Union[str, Sequence[str], None] = '0012_gantt_import_db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'gantt_plan',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('proiect_id', sa.Integer(), nullable=True),
        sa.Column('nume', sa.String(length=160), nullable=False),
        sa.Column('nume_fisier', sa.String(length=255), nullable=True),
        sa.Column('ext', sa.String(length=10), nullable=True),
        sa.Column('continut', sa.LargeBinary(), nullable=False),
        sa.Column('mapare_json', sa.Text(), nullable=True),
        sa.Column('data_start', sa.Date(), nullable=True),
        sa.Column('nr_activitati', sa.Integer(), nullable=False),
        sa.Column('durata_zile', sa.Integer(), nullable=False),
        sa.Column('cost_total', sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column('creat_de_id', sa.Integer(), nullable=True),
        sa.Column('data_creare', sa.DateTime(), nullable=False),
        sa.Column('data_actualizare', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['creat_de_id'], ['utilizatori.id'], ),
        sa.ForeignKeyConstraint(['proiect_id'], ['proiecte.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('gantt_plan', schema=None) as batch_op:
        batch_op.create_index('ix_gantt_plan_tenant_proiect',
                              ['tenant_id', 'proiect_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_gantt_plan_proiect_id'),
                              ['proiect_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_gantt_plan_tenant_id'),
                              ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_table('gantt_plan')
