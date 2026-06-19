"""0029 pontaj spor noapte (coloana aditiva ore de noapte)

Revision ID: 0029_pontaj_spor_noapte
Revises: 0028_gantt_tracking
Create Date: 2026-06-19 00:00:00.000000

Workforce Faza 2: spor de noapte la pontaj.
Adauga o coloana aditiva nullable pe tabela existenta 'pontaje':
- spor_noapte (NUMERIC(5,2)) - ore lucrate in fereastra legala 22:00-06:00
  (baza pentru sporul de noapte, min 25% conform Codului Muncii).

Coloana se populeaza doar cand flag-ul 'pontaj-spor-noapte' e activ
(vezi services/sporuri.py); cu flag OFF ramane NULL (comportament istoric).

Strict aditiv - pe prod se aplica prin migrate-bim (ALTER idempotent),
NU prin alembic upgrade (vezi CLAUDE.md - alembic desincronizat pe prod).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0029_pontaj_spor_noapte'
down_revision: Union[str, Sequence[str], None] = '0028_gantt_tracking'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('pontaje', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('spor_noapte', sa.Numeric(precision=5, scale=2), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table('pontaje', schema=None) as batch_op:
        batch_op.drop_column('spor_noapte')
