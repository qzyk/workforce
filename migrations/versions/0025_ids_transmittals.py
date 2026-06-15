"""0025 IDS validator + transmittals ISO 19650

Revision ID: 0025_ids_transmittals
Revises: 0024_issue_viewpoint
Create Date: 2026-06-16 00:00:00.000000

Faza 5a BIM: governance de livrare informationala.
- CREATE TABLE bim_ids_spec - specificatie IDS (Information Delivery
  Specification): ce clase IFC / Pset-uri + proprietati sunt CERUTE pe o
  faza de livrare ISO 19650 (proiectare / executie / predare).
- CREATE TABLE bim_ids_violation - neconformitate fata de o IDS spec
  (analog bim_rule_violations).
- CREATE TABLE bim_transmittal - transmittal ISO 19650 (tracking livrare:
  cine a primit ce versiune de model, cand). Adaugat in acelasi 0025 ca head unic.

Strict aditiv - pe prod se aplica prin migrate-bim (db.create_all pentru
tabelele noi), NU prin alembic upgrade (vezi CLAUDE.md - alembic desincronizat
pe prod).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0025_ids_transmittals'
down_revision: Union[str, Sequence[str], None] = '0024_issue_viewpoint'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. IDS spec (PARTEA 1)
    op.create_table(
        'bim_ids_spec',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('nume', sa.String(length=200), nullable=False),
        sa.Column('descriere', sa.Text(), nullable=True),
        sa.Column('faza', sa.String(length=30), nullable=False),
        sa.Column('definitie_json', sa.Text(), nullable=False),
        sa.Column('activ', sa.Boolean(), nullable=False),
        sa.Column('data_creare', sa.DateTime(), nullable=False),
        sa.Column('creat_de_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['creat_de_id'], ['utilizatori.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('bim_ids_spec', schema=None) as batch_op:
        batch_op.create_index('ix_bim_ids_spec_tenant_id', ['tenant_id'])
        batch_op.create_index('ix_bim_ids_spec_faza', ['faza'])
        batch_op.create_index('ix_bim_ids_spec_activ', ['activ'])

    # 2. IDS violation (PARTEA 1)
    op.create_table(
        'bim_ids_violation',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('spec_id', sa.Integer(), nullable=False),
        sa.Column('element_bim_id', sa.Integer(), nullable=True),
        sa.Column('run_id', sa.String(length=36), nullable=True),
        sa.Column('mesaj', sa.String(length=500), nullable=False),
        sa.Column('severitate', sa.String(length=20), nullable=False),
        sa.Column('detalii_json', sa.Text(), nullable=True),
        sa.Column('data_detectie', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['spec_id'], ['bim_ids_spec.id']),
        sa.ForeignKeyConstraint(['element_bim_id'], ['bim_elemente.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('bim_ids_violation', schema=None) as batch_op:
        batch_op.create_index('ix_bim_ids_violation_tenant_id', ['tenant_id'])
        batch_op.create_index('ix_bim_ids_violation_spec_id', ['spec_id'])
        batch_op.create_index('ix_bim_ids_violation_element_bim_id', ['element_bim_id'])
        batch_op.create_index('ix_bim_ids_violation_run_id', ['run_id'])
        batch_op.create_index('ix_bim_ids_violation_severitate', ['severitate'])
        batch_op.create_index('ix_bim_ids_violation_data_detectie', ['data_detectie'])
        batch_op.create_index('ix_ids_violation_spec_run', ['spec_id', 'run_id'])

    # 3. Transmittals ISO 19650 (PARTEA 2) - tabela bim_transmittal, in acelasi
    # 0025 ca head unic.
    op.create_table(
        'bim_transmittal',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('model_version_id', sa.Integer(), nullable=False),
        sa.Column('cod', sa.String(length=50), nullable=False),
        sa.Column('nume', sa.String(length=200), nullable=True),
        sa.Column('destinatari_json', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('observatii', sa.Text(), nullable=True),
        sa.Column('creat_de_id', sa.Integer(), nullable=True),
        sa.Column('data_creare', sa.DateTime(), nullable=False),
        sa.Column('data_trimitere', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['model_version_id'], ['bim_model_versions.id']),
        sa.ForeignKeyConstraint(['creat_de_id'], ['utilizatori.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('bim_transmittal', schema=None) as batch_op:
        batch_op.create_index('ix_bim_transmittal_tenant_id', ['tenant_id'])
        batch_op.create_index('ix_bim_transmittal_model_version_id', ['model_version_id'])
        batch_op.create_index('ix_bim_transmittal_status', ['status'])
        batch_op.create_index('ix_bim_transmittal_data_creare', ['data_creare'])


def downgrade() -> None:
    with op.batch_alter_table('bim_transmittal', schema=None) as batch_op:
        batch_op.drop_index('ix_bim_transmittal_data_creare')
        batch_op.drop_index('ix_bim_transmittal_status')
        batch_op.drop_index('ix_bim_transmittal_model_version_id')
        batch_op.drop_index('ix_bim_transmittal_tenant_id')
    op.drop_table('bim_transmittal')

    with op.batch_alter_table('bim_ids_violation', schema=None) as batch_op:
        batch_op.drop_index('ix_ids_violation_spec_run')
        batch_op.drop_index('ix_bim_ids_violation_data_detectie')
        batch_op.drop_index('ix_bim_ids_violation_severitate')
        batch_op.drop_index('ix_bim_ids_violation_run_id')
        batch_op.drop_index('ix_bim_ids_violation_element_bim_id')
        batch_op.drop_index('ix_bim_ids_violation_spec_id')
        batch_op.drop_index('ix_bim_ids_violation_tenant_id')
    op.drop_table('bim_ids_violation')

    with op.batch_alter_table('bim_ids_spec', schema=None) as batch_op:
        batch_op.drop_index('ix_bim_ids_spec_activ')
        batch_op.drop_index('ix_bim_ids_spec_faza')
        batch_op.drop_index('ix_bim_ids_spec_tenant_id')
    op.drop_table('bim_ids_spec')
