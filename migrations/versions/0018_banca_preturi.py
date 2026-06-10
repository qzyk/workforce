"""0018 banca_preturi

Revision ID: 0018_banca_preturi
Revises: 0017_extras_resursa
Create Date: 2026-06-09 12:00:00.000000

Banca de preturi de resurse (referinta din extrase reale C6/C7/C8/C9/F4).
Tabel NOU (strict aditiv) - pe prod: db.create_all() + alembic stamp head
(NU alembic upgrade). Migratia exista pt. paritatea alembic-head == create_all
(test_alembic_baseline).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0018_banca_preturi'
down_revision: Union[str, Sequence[str], None] = '0017_extras_resursa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'pret_resursa',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('tip', sa.String(length=12), nullable=False),
        sa.Column('cod', sa.String(length=80), nullable=False),
        sa.Column('denumire', sa.String(length=400), nullable=False),
        sa.Column('um', sa.String(length=20), nullable=True),
        sa.Column('pret_unitar', sa.Numeric(16, 4), nullable=False),
        sa.Column('moneda', sa.String(length=8), nullable=False),
        sa.Column('sursa', sa.String(length=200), nullable=True),
        sa.Column('proiect_id', sa.Integer(), nullable=True),
        sa.Column('data_pret', sa.Date(), nullable=True),
        sa.Column('furnizor', sa.String(length=150), nullable=True),
        sa.Column('introdus_de', sa.Integer(), nullable=True),
        sa.Column('data_creare', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.ForeignKeyConstraint(['proiect_id'], ['proiecte.id'], ),
        sa.ForeignKeyConstraint(['introdus_de'], ['utilizatori.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('pret_resursa', schema=None) as batch_op:
        batch_op.create_index('ix_pret_resursa_tenant_id', ['tenant_id'], unique=False)
        batch_op.create_index('ix_pret_resursa_tip', ['tip'], unique=False)
        batch_op.create_index('ix_pret_resursa_cod', ['cod'], unique=False)
        batch_op.create_index('ix_pret_resursa_sursa', ['sursa'], unique=False)
        batch_op.create_index('ix_pret_resursa_proiect_id', ['proiect_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('pret_resursa', schema=None) as batch_op:
        batch_op.drop_index('ix_pret_resursa_proiect_id')
        batch_op.drop_index('ix_pret_resursa_sursa')
        batch_op.drop_index('ix_pret_resursa_cod')
        batch_op.drop_index('ix_pret_resursa_tip')
        batch_op.drop_index('ix_pret_resursa_tenant_id')
    op.drop_table('pret_resursa')
