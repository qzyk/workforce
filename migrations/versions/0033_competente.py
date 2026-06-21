"""0033 competente + angajat_competenta (skill matrix Workforce Faza 3)

Revision ID: 0033_competente
Revises: 0032_rollup_watermark
Create Date: 2026-06-21 00:00:00.000000

Workforce Faza 3: competente structurate + matching.
Adauga doua tabele noi (strict aditiv, PK Integer, tenant nullable):
- competente: nomenclator (nume, categorie, descriere, certificare, valabilitate).
- angajat_competenta: legatura M:N angajat <-> competenta (nivel 1-5,
  data_obtinere, data_expirare nullable), cu index unic (angajat_id, competenta_id).

Tabelele se folosesc doar cand flag-ul 'competente' e activ (UI/rute gated OFF
intorc 404). Pe prod se aplica prin migrate-bim (db.create_all, tabele noi),
NU prin alembic upgrade (vezi CLAUDE.md - alembic desincronizat pe prod).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0033_competente'
down_revision: Union[str, Sequence[str], None] = '0032_rollup_watermark'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'competente',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('nume', sa.String(length=150), nullable=False),
        sa.Column('categorie', sa.String(length=80), nullable=True),
        sa.Column('descriere', sa.Text(), nullable=True),
        sa.Column('necesita_certificare', sa.Boolean(), nullable=True),
        sa.Column('valabilitate_luni', sa.Integer(), nullable=True),
        sa.Column('activ', sa.Boolean(), nullable=True),
        sa.Column('data_creare', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('competente', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_competente_tenant_id'), ['tenant_id'], unique=False
        )

    op.create_table(
        'angajat_competenta',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('angajat_id', sa.Integer(), nullable=False),
        sa.Column('competenta_id', sa.Integer(), nullable=False),
        sa.Column('nivel', sa.Integer(), nullable=True),
        sa.Column('data_obtinere', sa.Date(), nullable=True),
        sa.Column('data_expirare', sa.Date(), nullable=True),
        sa.Column('observatii', sa.Text(), nullable=True),
        sa.Column('data_creare', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['angajat_id'], ['angajati.id'], ),
        sa.ForeignKeyConstraint(['competenta_id'], ['competente.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('angajat_id', 'competenta_id', name='uq_angajat_competenta'),
    )


def downgrade() -> None:
    op.drop_table('angajat_competenta')
    with op.batch_alter_table('competente', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_competente_tenant_id'))
    op.drop_table('competente')
