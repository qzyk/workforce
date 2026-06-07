"""0018 ifc_qto_columns

Revision ID: 0018_ifc_qto_columns
Revises: 0017_extras_resursa
Create Date: 2026-06-08 12:00:00.000000

Coloane QTO harvest pe bim_elemente (Etapa 1: punte IFC -> F3). Strict aditiv.
Pe prod (BIM gestionat via create_all + migrate-bim): db.create_all() +
alembic stamp head, NU alembic upgrade. Migratia exista pt. paritatea
alembic-head == create_all (test_alembic_baseline).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0018_ifc_qto_columns'
down_revision: Union[str, Sequence[str], None] = '0017_extras_resursa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('bim_elemente', schema=None) as batch_op:
        batch_op.add_column(sa.Column('qto_sursa', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('qto_set', sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column('cod_deviz', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('clasificare_sursa', sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column('necesita_verificare', sa.Boolean(),
                                      nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('motiv_verificare', sa.String(length=120), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('bim_elemente', schema=None) as batch_op:
        batch_op.drop_column('motiv_verificare')
        batch_op.drop_column('necesita_verificare')
        batch_op.drop_column('clasificare_sursa')
        batch_op.drop_column('cod_deviz')
        batch_op.drop_column('qto_set')
        batch_op.drop_column('qto_sursa')
