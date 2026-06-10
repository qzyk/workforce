"""0018 obiectiv_obiect

Revision ID: 0018_obiectiv_obiect
Revises: 0017_extras_resursa
Create Date: 2026-06-09 13:00:00.000000

Ierarhia obiectiv: Obiectiv (F1) -> Obiect (F2) -> GanttPlan (F3).
Tabele NOI (obiectiv, obiect) + coloana obiect_id pe gantt_plan. Strict aditiv.
Pe prod: db.create_all() + alembic stamp head (NU alembic upgrade).
Migratia exista pt. paritatea alembic-head == create_all (test_alembic_baseline).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0018_obiectiv_obiect'
down_revision: Union[str, Sequence[str], None] = '0017_extras_resursa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'obiectiv',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('proiect_id', sa.Integer(), nullable=True),
        sa.Column('cod', sa.String(length=50), nullable=True),
        sa.Column('nume', sa.String(length=250), nullable=False),
        sa.Column('descriere', sa.Text(), nullable=True),
        sa.Column('valoare_constructii', sa.Numeric(16, 2), nullable=True),
        sa.Column('valoare_totala', sa.Numeric(16, 2), nullable=True),
        sa.Column('valoare_cm', sa.Numeric(16, 2), nullable=True),
        sa.Column('data', sa.Date(), nullable=True),
        sa.Column('nume_fisier_f1', sa.String(length=255), nullable=True),
        sa.Column('creat_de_id', sa.Integer(), nullable=True),
        sa.Column('data_creare', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.ForeignKeyConstraint(['proiect_id'], ['proiecte.id'], ),
        sa.ForeignKeyConstraint(['creat_de_id'], ['utilizatori.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('obiectiv', schema=None) as batch_op:
        batch_op.create_index('ix_obiectiv_tenant_id', ['tenant_id'], unique=False)
        batch_op.create_index('ix_obiectiv_proiect_id', ['proiect_id'], unique=False)

    op.create_table(
        'obiect',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('obiectiv_id', sa.Integer(), nullable=False),
        sa.Column('cod', sa.String(length=20), nullable=True),
        sa.Column('nume', sa.String(length=250), nullable=False),
        sa.Column('disciplina', sa.String(length=40), nullable=True),
        sa.Column('valoare_f2', sa.Numeric(16, 2), nullable=True),
        sa.Column('valoare_f1', sa.Numeric(16, 2), nullable=True),
        sa.Column('ordine', sa.Integer(), nullable=False),
        sa.Column('nume_fisier_f2', sa.String(length=255), nullable=True),
        sa.Column('data_creare', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.ForeignKeyConstraint(['obiectiv_id'], ['obiectiv.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('obiect', schema=None) as batch_op:
        batch_op.create_index('ix_obiect_tenant_id', ['tenant_id'], unique=False)
        batch_op.create_index('ix_obiect_obiectiv_id', ['obiectiv_id'], unique=False)

    with op.batch_alter_table('gantt_plan', schema=None) as batch_op:
        batch_op.add_column(sa.Column('obiect_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_gantt_plan_obiect_id', ['obiect_id'], unique=False)
        batch_op.create_foreign_key('fk_gantt_plan_obiect', 'obiect', ['obiect_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('gantt_plan', schema=None) as batch_op:
        batch_op.drop_constraint('fk_gantt_plan_obiect', type_='foreignkey')
        batch_op.drop_index('ix_gantt_plan_obiect_id')
        batch_op.drop_column('obiect_id')

    with op.batch_alter_table('obiect', schema=None) as batch_op:
        batch_op.drop_index('ix_obiect_obiectiv_id')
        batch_op.drop_index('ix_obiect_tenant_id')
    op.drop_table('obiect')

    with op.batch_alter_table('obiectiv', schema=None) as batch_op:
        batch_op.drop_index('ix_obiectiv_proiect_id')
        batch_op.drop_index('ix_obiectiv_tenant_id')
    op.drop_table('obiectiv')
