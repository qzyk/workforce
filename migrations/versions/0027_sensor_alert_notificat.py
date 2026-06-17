"""0027 sensor alert notificat_la (idempotenta dispatch notificare)

Revision ID: 0027_sensor_alert_notificat
Revises: 0026_concedii_workflow
Create Date: 2026-06-17 00:00:00.000000

IoT Faza 1: inchiderea buclei alerta senzor -> notificare (in-app + SSE + email).
Adauga o coloana aditiva nullable pe tabela existenta 'bim_sensor_alerts':
- notificat_la (DATETIME) - momentul in care alerta a fost notificata; NULL =
  inca nenotificata. Folosit pentru idempotenta dispatch-ului.

Strict aditiv - pe prod se aplica prin migrate-bim (ALTER idempotent),
NU prin alembic upgrade (vezi CLAUDE.md - alembic desincronizat pe prod).

NOTA: pe acest branch (feat/iot-1-alert-notify) baza este feat/dz-1-evm-prognoza,
care contine deja 0026_concedii_workflow chained pe 0025_ids_transmittals.
Aceasta revizie continua lant-ul liniar dupa 0026.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0027_sensor_alert_notificat'
down_revision: Union[str, Sequence[str], None] = '0026_concedii_workflow'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('bim_sensor_alerts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('notificat_la', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('bim_sensor_alerts', schema=None) as batch_op:
        batch_op.drop_column('notificat_la')
