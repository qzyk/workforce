"""0036 sensor offline_timeout_sec (detectie senzor offline)

Revision ID: 0036_sensor_offline_timeout
Revises: 0035_situatie_retentii_manual
Create Date: 2026-06-22 00:00:00.000000

IoT Faza 3: detectie senzor offline + batch ingest.
Adauga o coloana aditiva nullable pe tabela existenta 'bim_senzori':
- offline_timeout_sec (INTEGER) - interval in secunde dupa care senzorul e
  considerat offline daca nu mai trimite citiri. NULL = detectie dezactivata
  pentru acest senzor. Folosit de iot_offline.check_offline (CLI
  'flask iot-offline'), care genereaza o alerta tip='offline' (de-dup pe alerta
  offline deschisa, reutilizeaza dispatch_alert din Faza 1).

Strict aditiv - pe prod se aplica prin migrate-bim (ALTER idempotent, in
link_targets cu verificare 'col in cols'), NU prin alembic upgrade (vezi
CLAUDE.md - alembic e desincronizat de schema reala pe prod) + alembic stamp head.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0036_sensor_offline_timeout'
down_revision: Union[str, Sequence[str], None] = '0035_situatie_retentii_manual'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('bim_senzori', schema=None) as batch_op:
        batch_op.add_column(sa.Column('offline_timeout_sec', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('bim_senzori', schema=None) as batch_op:
        batch_op.drop_column('offline_timeout_sec')
