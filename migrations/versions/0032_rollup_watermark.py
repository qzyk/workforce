"""0032 rollup watermark pe inserare (created_at + last_rollup_at)

Revision ID: 0032_rollup_watermark
Revises: 0031_sensor_rollup
Create Date: 2026-06-20 00:30:00.000000

IoT Faza 2 (fix review): watermark-ul incremental al rollup-ului se muta de pe
timpul MASURARII (ts, care poate fi backdatat la ingest) pe momentul INSERARII.
Doua coloane aditive nullable pe tabele existente:
- bim_sensor_readings.created_at (DATETIME) - momentul inserarii citirii. NULL =
  randuri vechi de dinainte de acest fix (recuperabile cu 'flask iot-rollup --full').
  Index (senzor_id, created_at) pentru watermark eficient.
- bim_senzori.last_rollup_at (DATETIME) - high-watermark al ultimei rulari de
  rollup per senzor. NULL = senzor nerollup-at inca (prima rulare proceseaza tot).

Astfel o citire late ingestata (ts vechi, created_at recent) intr-un bucket vechi
DEJA inchis e prinsa la urmatoarea rulare 'flask iot-rollup' (filtram pe
created_at, nu pe ts) -> echivalenta rollup==Python pastrata indiferent de varsta
bucket-ului citirii late.

Strict aditiv - pe prod se aplica prin migrate-bim (ALTER idempotent), NU prin
alembic upgrade (vezi CLAUDE.md - alembic desincronizat pe prod). Aceasta revizie
continua lant-ul liniar dupa 0031_sensor_rollup.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0032_rollup_watermark'
down_revision: Union[str, Sequence[str], None] = '0031_sensor_rollup'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('bim_sensor_readings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_bim_sensor_readings_created_at', ['created_at'])
        batch_op.create_index('ix_reading_senzor_created',
                              ['senzor_id', 'created_at'])

    with op.batch_alter_table('bim_senzori', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_rollup_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('bim_senzori', schema=None) as batch_op:
        batch_op.drop_column('last_rollup_at')

    with op.batch_alter_table('bim_sensor_readings', schema=None) as batch_op:
        batch_op.drop_index('ix_reading_senzor_created')
        batch_op.drop_index('ix_bim_sensor_readings_created_at')
        batch_op.drop_column('created_at')
