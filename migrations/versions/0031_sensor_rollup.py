"""0031 sensor rollup (downsampling time-series pre-calculat)

Revision ID: 0031_sensor_rollup
Revises: 0030_evm_baseline
Create Date: 2026-06-20 00:00:00.000000

IoT Faza 2: scalabilitate time-series. Tabel nou 'bim_sensor_rollup' care
materializeaza agregarea (min/max/avg/count) per (senzor, bucket, bucket_ts).
Inlocuieste agregarea Python in-memory din iot_query.get_history (care incarca
toate citirile -> risc OOM/timeout) cu o citire directa din rollup pentru
agg='1h'/'1d'.

Idempotenta rollup-ului: index UNIC (senzor_id, bucket, bucket_ts) -> re-rularea
'flask iot-rollup' face UPSERT pe bucket, nu dubleaza randuri.

Tabel nou strict aditiv - PK Integer (auto-increment cross-dialect), tenant_id
nullable. Pe prod se aplica prin migrate-bim (db.create_all idempotent), NU prin
alembic upgrade (vezi CLAUDE.md - alembic desincronizat pe prod). Aceasta revizie
continua lant-ul liniar dupa 0030_evm_baseline.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0031_sensor_rollup'
down_revision: Union[str, Sequence[str], None] = '0030_evm_baseline'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'bim_sensor_rollup',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('senzor_id', sa.Integer(), nullable=False),
        sa.Column('bucket', sa.String(length=4), nullable=False),
        sa.Column('bucket_ts', sa.DateTime(), nullable=False),
        sa.Column('v_min', sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column('v_max', sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column('v_avg', sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column('v_count', sa.Integer(), nullable=False),
        sa.Column('data_creare', sa.DateTime(), nullable=False),
        sa.Column('data_modificare', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['senzor_id'], ['bim_senzori.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('senzor_id', 'bucket', 'bucket_ts',
                            name='uix_rollup_senzor_bucket_ts'),
    )
    with op.batch_alter_table('bim_sensor_rollup', schema=None) as batch_op:
        batch_op.create_index('ix_bim_sensor_rollup_tenant_id', ['tenant_id'])
        batch_op.create_index('ix_bim_sensor_rollup_senzor_id', ['senzor_id'])


def downgrade() -> None:
    with op.batch_alter_table('bim_sensor_rollup', schema=None) as batch_op:
        batch_op.drop_index('ix_bim_sensor_rollup_senzor_id')
        batch_op.drop_index('ix_bim_sensor_rollup_tenant_id')
    op.drop_table('bim_sensor_rollup')
