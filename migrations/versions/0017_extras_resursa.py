"""0017 extras_resursa

Revision ID: 0017_extras_resursa
Revises: 0016_gantt_wbs_nod
Create Date: 2026-06-03 12:00:00.000000

Extrase de resurse din deviz (C6 materiale / C7 manopera / C8 utilaje) pe proiect.
Tabel NOU (strict aditiv) - pe prod: db.create_all() + alembic stamp head
(NU alembic upgrade).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0017_extras_resursa'
down_revision: Union[str, Sequence[str], None] = '0016_gantt_wbs_nod'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'extras_resursa',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('proiect_id', sa.Integer(), nullable=False),
        sa.Column('tip', sa.String(length=12), nullable=False),
        sa.Column('cod', sa.String(length=60), nullable=True),
        sa.Column('denumire', sa.String(length=400), nullable=False),
        sa.Column('um', sa.String(length=20), nullable=True),
        sa.Column('cantitate', sa.Numeric(16, 3), nullable=False),
        sa.Column('tarif_unitar', sa.Numeric(14, 4), nullable=False),
        sa.Column('valoare', sa.Numeric(16, 2), nullable=False),
        sa.Column('furnizor', sa.String(length=150), nullable=True),
        sa.Column('nume_fisier', sa.String(length=255), nullable=True),
        sa.Column('introdus_de', sa.Integer(), nullable=True),
        sa.Column('data_creare', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.ForeignKeyConstraint(['proiect_id'], ['proiecte.id'], ),
        sa.ForeignKeyConstraint(['introdus_de'], ['utilizatori.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('extras_resursa', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_extras_resursa_tenant_id'),
                              ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_extras_resursa_proiect_id'),
                              ['proiect_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_extras_resursa_tip'),
                              ['tip'], unique=False)


def downgrade() -> None:
    op.drop_table('extras_resursa')
