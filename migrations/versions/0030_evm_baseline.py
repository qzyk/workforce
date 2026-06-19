"""0030 evm_baseline

Revision ID: 0030_evm_baseline
Revises: 0029_pontaj_spor_noapte
Create Date: 2026-06-19 00:00:00.000000

Baseline EVM materializat (PMB - Performance Measurement Baseline), Deviz Faza 2.
Inghetam curba PLANIFICATA (PV) + BAC la aprobarea programului ca sa nu le mai
recalculam live (re-rularea pipeline-ului Gantt) la fiecare cerere EVM (fragil + lent).

Strict aditiv: 1 tabel nou (evm_baseline) + 1 coloana nullable pe tabela existenta
(proiecte.baseline_evm_activ_id, FK la evm_baseline). Pe prod se aplica prin
db.create_all() + ALTER idempotent (CLI migrate-bim) + alembic stamp head
(NU alembic upgrade).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0030_evm_baseline'
down_revision: Union[str, Sequence[str], None] = '0029_pontaj_spor_noapte'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) evm_baseline (snapshot PV + BAC inghetat la aprobarea programului)
    op.create_table(
        'evm_baseline',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('proiect_id', sa.Integer(), nullable=False),
        sa.Column('nume', sa.String(length=120), nullable=False),
        sa.Column('data_creare', sa.DateTime(), nullable=False),
        sa.Column('creat_de_id', sa.Integer(), nullable=True),
        sa.Column('bac', sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column('continut_json', sa.Text(), nullable=False),
        sa.Column('activ', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.ForeignKeyConstraint(['proiect_id'], ['proiecte.id'], ),
        sa.ForeignKeyConstraint(['creat_de_id'], ['utilizatori.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('evm_baseline', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_evm_baseline_tenant_id'),
                              ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_evm_baseline_proiect_id'),
                              ['proiect_id'], unique=False)
        batch_op.create_index('ix_evm_baseline_proiect_activ',
                              ['proiect_id', 'activ'], unique=False)

    # 2) coloana noua NULLABLE pe tabela existenta 'proiecte'
    with op.batch_alter_table('proiecte', schema=None) as batch_op:
        batch_op.add_column(sa.Column('baseline_evm_activ_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_proiect_baseline_evm_activ', 'evm_baseline',
                                    ['baseline_evm_activ_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('proiecte', schema=None) as batch_op:
        batch_op.drop_constraint('fk_proiect_baseline_evm_activ', type_='foreignkey')
        batch_op.drop_column('baseline_evm_activ_id')

    with op.batch_alter_table('evm_baseline', schema=None) as batch_op:
        batch_op.drop_index('ix_evm_baseline_proiect_activ')
        batch_op.drop_index(batch_op.f('ix_evm_baseline_proiect_id'))
        batch_op.drop_index(batch_op.f('ix_evm_baseline_tenant_id'))
    op.drop_table('evm_baseline')
