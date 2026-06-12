"""0018 gantt_calendar

Revision ID: 0018_gantt_calendar
Revises: 0017_extras_resursa
Create Date: 2026-06-12 00:00:00.000000

Calendar de lucru pentru Gantt (Faza 1): sablon saptamanal + exceptii pe date
(sarbatori legale / sambete lucratoare) + legatura optionala plan -> calendar.
Strict aditiv (2 tabele noi + 1 coloana nullable) - pe prod se aplica prin
db.create_all() + alembic stamp head (NU alembic upgrade).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0018_gantt_calendar'
down_revision: Union[str, Sequence[str], None] = '0017_extras_resursa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'gantt_calendar',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('nume', sa.String(length=120), nullable=False),
        sa.Column('zile_lucratoare', sa.String(length=7), nullable=False),
        sa.Column('ore_pe_zi', sa.Integer(), nullable=False),
        sa.Column('implicit', sa.Boolean(), nullable=False),
        sa.Column('activ', sa.Boolean(), nullable=False),
        sa.Column('creat_de_id', sa.Integer(), nullable=True),
        sa.Column('data_creare', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.ForeignKeyConstraint(['creat_de_id'], ['utilizatori.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('gantt_calendar', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_gantt_calendar_tenant_id'),
                              ['tenant_id'], unique=False)

    op.create_table(
        'gantt_calendar_exceptie',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('calendar_id', sa.Integer(), nullable=False),
        sa.Column('data', sa.Date(), nullable=False),
        sa.Column('lucratoare', sa.Boolean(), nullable=False),
        sa.Column('descriere', sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(['calendar_id'], ['gantt_calendar.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('calendar_id', 'data', name='uix_gantt_calendar_exceptie'),
    )
    with op.batch_alter_table('gantt_calendar_exceptie', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_gantt_calendar_exceptie_calendar_id'),
                              ['calendar_id'], unique=False)

    # coloana noua NULLABLE pe gantt_plan: calendarul de lucru al planului
    with op.batch_alter_table('gantt_plan', schema=None) as batch_op:
        batch_op.add_column(sa.Column('calendar_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_gantt_plan_calendar_id', 'gantt_calendar',
                                    ['calendar_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('gantt_plan', schema=None) as batch_op:
        batch_op.drop_constraint('fk_gantt_plan_calendar_id', type_='foreignkey')
        batch_op.drop_column('calendar_id')
    op.drop_table('gantt_calendar_exceptie')
    op.drop_table('gantt_calendar')
