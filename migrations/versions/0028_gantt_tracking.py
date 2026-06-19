"""0028 gantt_tracking

Revision ID: 0028_gantt_tracking
Revises: 0027_sensor_alert_notificat
Create Date: 2026-06-19 00:00:00.000000

Strat de urmarire a executiei pentru Gantt (Faza 2): baseline (plan de referinta
inghetat) + progres fizic pe activitate (append-only), pe cheia stabila de
activitate (independenta de ordinea randurilor din F3).

Strict aditiv: 2 tabele noi + 3 coloane nullable pe tabele existente
(gantt_plan.baseline_activ_id, gantt_wbs_nod.cheie_activitate,
bim_task_schedules.cheie_activitate). Pe prod se aplica prin db.create_all() +
ALTER idempotent (CLI migrate-bim) + alembic stamp head (NU alembic upgrade).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0028_gantt_tracking'
down_revision: Union[str, Sequence[str], None] = '0027_sensor_alert_notificat'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) gantt_baseline (plan de referinta inghetat)
    op.create_table(
        'gantt_baseline',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('nume', sa.String(length=120), nullable=False),
        sa.Column('data_creare', sa.DateTime(), nullable=False),
        sa.Column('creat_de_id', sa.Integer(), nullable=True),
        sa.Column('bac', sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column('durata_zile', sa.Integer(), nullable=False),
        sa.Column('data_start', sa.Date(), nullable=True),
        sa.Column('continut_json', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.ForeignKeyConstraint(['plan_id'], ['gantt_plan.id'], ),
        sa.ForeignKeyConstraint(['creat_de_id'], ['utilizatori.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('gantt_baseline', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_gantt_baseline_tenant_id'),
                              ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_gantt_baseline_plan_id'),
                              ['plan_id'], unique=False)

    # 2) gantt_progres (jurnal append-only de progres fizic)
    op.create_table(
        'gantt_progres',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('cheie_activitate', sa.String(length=64), nullable=False),
        sa.Column('data', sa.Date(), nullable=False),
        sa.Column('procent_fizic', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('cantitate_realizata', sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column('data_start_real', sa.Date(), nullable=True),
        sa.Column('data_finish_real', sa.Date(), nullable=True),
        sa.Column('sursa', sa.String(length=20), nullable=False),
        sa.Column('creat_de_id', sa.Integer(), nullable=True),
        sa.Column('data_creare', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.ForeignKeyConstraint(['plan_id'], ['gantt_plan.id'], ),
        sa.ForeignKeyConstraint(['creat_de_id'], ['utilizatori.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('gantt_progres', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_gantt_progres_tenant_id'),
                              ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_gantt_progres_plan_id'),
                              ['plan_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_gantt_progres_cheie_activitate'),
                              ['cheie_activitate'], unique=False)
        batch_op.create_index('ix_gantt_progres_plan_cheie',
                              ['plan_id', 'cheie_activitate'], unique=False)

    # 3) coloane noi NULLABLE pe tabele existente
    with op.batch_alter_table('gantt_plan', schema=None) as batch_op:
        batch_op.add_column(sa.Column('baseline_activ_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_gantt_plan_baseline_activ', 'gantt_baseline',
                                    ['baseline_activ_id'], ['id'])

    with op.batch_alter_table('gantt_wbs_nod', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cheie_activitate', sa.String(length=64), nullable=True))

    with op.batch_alter_table('bim_task_schedules', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cheie_activitate', sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f('ix_bim_task_schedules_cheie_activitate'),
                              ['cheie_activitate'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('bim_task_schedules', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_bim_task_schedules_cheie_activitate'))
        batch_op.drop_column('cheie_activitate')

    with op.batch_alter_table('gantt_wbs_nod', schema=None) as batch_op:
        batch_op.drop_column('cheie_activitate')

    with op.batch_alter_table('gantt_plan', schema=None) as batch_op:
        batch_op.drop_constraint('fk_gantt_plan_baseline_activ', type_='foreignkey')
        batch_op.drop_column('baseline_activ_id')

    op.drop_table('gantt_progres')
    op.drop_table('gantt_baseline')
