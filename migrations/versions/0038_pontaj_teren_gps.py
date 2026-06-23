"""0038 pontaj teren GPS (coloane aditive geolocatie pe pontaje)

Revision ID: 0038_pontaj_teren_gps
Revises: 0037_raport_istoric_tenant
Create Date: 2026-06-23 00:00:00.000000

Workforce wf-4: pontaj de echipa pe teren + GPS optional.
Adauga trei coloane aditive nullable pe tabela existenta 'pontaje':
- latitudine (FLOAT)   - latitudinea capturata client-side (navigator.geolocation)
- longitudine (FLOAT)  - longitudinea capturata client-side
- sursa_gps (VARCHAR(10)) - 'gps' / 'manual' / NULL (provenienta coordonatelor)

Captura GPS e OPTIONALA: lipsa GPS NU blocheaza pontajul (coloanele raman NULL,
comportament istoric). Se populeaza doar pe calea bulk de teren cand flag-ul
'teren-pontaj-bulk' e activ; cu flag OFF raman NULL.

Strict aditiv - pe prod se aplica prin migrate-bim (ALTER idempotent),
NU prin alembic upgrade (vezi CLAUDE.md - alembic desincronizat pe prod).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0038_pontaj_teren_gps'
down_revision: Union[str, Sequence[str], None] = '0037_raport_istoric_tenant'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('pontaje', schema=None) as batch_op:
        batch_op.add_column(sa.Column('latitudine', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('longitudine', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('sursa_gps', sa.String(length=10), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('pontaje', schema=None) as batch_op:
        batch_op.drop_column('sursa_gps')
        batch_op.drop_column('longitudine')
        batch_op.drop_column('latitudine')
