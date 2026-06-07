"""0018 audit_deviz

Revision ID: 0018_audit_deviz
Revises: 0017_extras_resursa
Create Date: 2026-06-07 12:00:00.000000

Audit deviz extern (F2 + F3 + C6/C7/C8/C9): reconciliere 3 niveluri, structura
de cost, anomalii. Tabele NOI (strict aditiv) - pe prod: db.create_all() +
alembic stamp head (NU alembic upgrade).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0018_audit_deviz'
down_revision: Union[str, Sequence[str], None] = '0017_extras_resursa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_deviz',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('proiect_id', sa.Integer(), nullable=True),
        sa.Column('nume', sa.String(length=200), nullable=False),
        sa.Column('nume_fisier', sa.String(length=255), nullable=True),
        sa.Column('total_f2', sa.Numeric(16, 2), nullable=True),
        sa.Column('total_f3', sa.Numeric(16, 2), nullable=True),
        sa.Column('tva', sa.Numeric(16, 2), nullable=True),
        sa.Column('total_cu_tva', sa.Numeric(16, 2), nullable=True),
        sa.Column('delta_reconciliere', sa.Numeric(16, 2), nullable=True),
        sa.Column('pct_material', sa.Numeric(6, 2), nullable=True),
        sa.Column('pct_manopera', sa.Numeric(6, 2), nullable=True),
        sa.Column('pct_utilaj', sa.Numeric(6, 2), nullable=True),
        sa.Column('pct_transport', sa.Numeric(6, 2), nullable=True),
        sa.Column('nr_obiecte', sa.Integer(), nullable=False),
        sa.Column('nr_anomalii', sa.Integer(), nullable=False),
        sa.Column('rezultat_json', sa.Text(), nullable=True),
        sa.Column('data_creare', sa.DateTime(), nullable=False),
        sa.Column('creat_de_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.ForeignKeyConstraint(['proiect_id'], ['proiecte.id'], ),
        sa.ForeignKeyConstraint(['creat_de_id'], ['utilizatori.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('audit_deviz', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_audit_deviz_tenant_id'),
                              ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_deviz_proiect_id'),
                              ['proiect_id'], unique=False)
        batch_op.create_index('ix_audit_deviz_proiect',
                              ['proiect_id', 'data_creare'], unique=False)

    op.create_table(
        'obiect_audit_deviz',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('audit_id', sa.Integer(), nullable=False),
        sa.Column('numar', sa.String(length=10), nullable=True),
        sa.Column('nume', sa.String(length=200), nullable=False),
        sa.Column('val_f3', sa.Numeric(16, 2), nullable=True),
        sa.Column('val_f2', sa.Numeric(16, 2), nullable=True),
        sa.Column('val_c6', sa.Numeric(16, 2), nullable=True),
        sa.Column('val_c7', sa.Numeric(16, 2), nullable=True),
        sa.Column('val_c8', sa.Numeric(16, 2), nullable=True),
        sa.Column('val_c9', sa.Numeric(16, 2), nullable=True),
        sa.Column('delta_l1', sa.Numeric(16, 2), nullable=True),
        sa.Column('delta_l2', sa.Numeric(16, 2), nullable=True),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.ForeignKeyConstraint(['audit_id'], ['audit_deviz.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('obiect_audit_deviz', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_obiect_audit_deviz_audit_id'),
                              ['audit_id'], unique=False)

    op.create_table(
        'anomalie_deviz',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('audit_id', sa.Integer(), nullable=False),
        sa.Column('obiect', sa.String(length=200), nullable=True),
        sa.Column('tip', sa.String(length=40), nullable=False),
        sa.Column('severitate', sa.String(length=12), nullable=False),
        sa.Column('mesaj', sa.String(length=400), nullable=False),
        sa.Column('valoare', sa.Numeric(16, 2), nullable=True),
        sa.ForeignKeyConstraint(['audit_id'], ['audit_deviz.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('anomalie_deviz', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_anomalie_deviz_audit_id'),
                              ['audit_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_anomalie_deviz_tip'),
                              ['tip'], unique=False)


def downgrade() -> None:
    op.drop_table('anomalie_deviz')
    op.drop_table('obiect_audit_deviz')
    op.drop_table('audit_deviz')
