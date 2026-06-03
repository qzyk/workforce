"""0015 consum_utilaj

Revision ID: 0015_consum_utilaj
Revises: 0014_proiect_santier
Create Date: 2026-06-02 23:00:00.000000

Consum real de utilaj pe proiect (Faza 3 - C: utilaj planificat vs real).
Tabel NOU (strict aditiv) - pe prod se aplica prin db.create_all() + alembic
stamp head (NU alembic upgrade, NU ALTER pe tabele existente).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0015_consum_utilaj'
down_revision: Union[str, Sequence[str], None] = '0014_proiect_santier'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'consum_utilaj',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('proiect_id', sa.Integer(), nullable=False),
        sa.Column('masina_id', sa.Integer(), nullable=True),
        sa.Column('denumire', sa.String(length=150), nullable=False),
        sa.Column('data', sa.Date(), nullable=False),
        sa.Column('ore', sa.Numeric(10, 2), nullable=False),
        sa.Column('tarif_ora', sa.Numeric(10, 2), nullable=False),
        sa.Column('cost', sa.Numeric(14, 2), nullable=False),
        sa.Column('categorie_lucrare', sa.String(length=60), nullable=True),
        sa.Column('observatii', sa.Text(), nullable=True),
        sa.Column('introdus_de', sa.Integer(), nullable=True),
        sa.Column('data_creare', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.ForeignKeyConstraint(['proiect_id'], ['proiecte.id'], ),
        sa.ForeignKeyConstraint(['masina_id'], ['masini.id'], ),
        sa.ForeignKeyConstraint(['introdus_de'], ['utilizatori.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('consum_utilaj', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_consum_utilaj_tenant_id'),
                              ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_consum_utilaj_proiect_id'),
                              ['proiect_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_consum_utilaj_masina_id'),
                              ['masina_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_consum_utilaj_data'),
                              ['data'], unique=False)


def downgrade() -> None:
    op.drop_table('consum_utilaj')
