"""0026 concedii workflow (coloane aditive pentru aprobare)

Revision ID: 0026_concedii_workflow
Revises: 0025_ids_transmittals
Create Date: 2026-06-17 00:00:00.000000

Workforce Faza 1: activarea modulului Concedii (modelul exista deja in models.py).
Adauga 3 coloane aditive nullable pe tabela existenta 'concedii' pentru workflow-ul
complet de aprobare:
- data_aprobare (DATETIME)         - momentul aprobarii / respingerii
- motiv_respingere (TEXT)          - nota la respingere
- introdus_de (INTEGER FK)         - utilizatorul care a creat cererea

Strict aditiv - pe prod se aplica prin migrate-bim (ALTER idempotent),
NU prin alembic upgrade (vezi CLAUDE.md - alembic desincronizat pe prod).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0026_concedii_workflow'
down_revision: Union[str, Sequence[str], None] = '0025_ids_transmittals'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('concedii', schema=None) as batch_op:
        batch_op.add_column(sa.Column('data_aprobare', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('motiv_respingere', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('introdus_de', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('concedii', schema=None) as batch_op:
        batch_op.drop_column('introdus_de')
        batch_op.drop_column('motiv_respingere')
        batch_op.drop_column('data_aprobare')
