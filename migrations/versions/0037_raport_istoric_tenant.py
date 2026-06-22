"""0037 rapoarte istoric robust (tenant + blob + checksum)

Revision ID: 0037_raport_istoric_tenant
Revises: 0036_sensor_offline_timeout
Create Date: 2026-06-22 12:00:00.000000

Rapoarte Faza 3: istoric robust. Adauga 3 coloane aditive nullable pe tabela
existenta 'rapoarte':
- tenant_id (INTEGER FK tenants.id) - izolare multi-tenant a istoricului.
  NULL = global = comportament actual (rapoartele vechi raman vizibile global).
- continut_blob (BLOB / LargeBinary) - copia binara a fisierului salvata in DB.
  Serveste descarcarea cand fisier_path nu mai exista pe disc (path absolut
  devine orfan dupa redeploy/restart pe PythonAnywhere). NULL = raport vechi
  fara blob (path-only, comportament backward-compat).
- checksum (VARCHAR(64)) - sha256 hex al continutului (integritate, optional).

Strict aditiv - pe prod se aplica prin migrate-bim (ALTER idempotent, in
link_targets cu verificare 'col in cols'), NU prin alembic upgrade (vezi
CLAUDE.md - alembic e desincronizat de schema reala pe prod) + alembic stamp head.
descarca() tolereaza NULL (blob lipsa -> serveste din path; ambele lipsa ->
regenereaza din parametri daca posibil), deci nicio migrare de date necesara.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0037_raport_istoric_tenant'
down_revision: Union[str, Sequence[str], None] = '0036_sensor_offline_timeout'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('rapoarte', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('continut_blob', sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column('checksum', sa.String(length=64), nullable=True))
        batch_op.create_index('ix_rapoarte_tenant_id', ['tenant_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_rapoarte_tenant_id', 'tenants', ['tenant_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('rapoarte', schema=None) as batch_op:
        batch_op.drop_constraint('fk_rapoarte_tenant_id', type_='foreignkey')
        batch_op.drop_index('ix_rapoarte_tenant_id')
        batch_op.drop_column('checksum')
        batch_op.drop_column('continut_blob')
        batch_op.drop_column('tenant_id')
