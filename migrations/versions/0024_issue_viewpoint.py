"""0024 issue viewpoint (view-state pe issue)

Revision ID: 0024_issue_viewpoint
Revises: 0023_clash_spatial_dedup
Create Date: 2026-06-15 00:00:00.000000

Faza 4 BIM: view-state pe issue pentru BCF Viewpoint round-trip.
- ADD COLUMN bim_issues.viewpoint_json (TEXT, NULLABLE) - camera + componente
  vizibile + clipping serializate JSON. Sursa pentru viewpoint.bcfv la export BCF.
Strict aditiv - pe prod se aplica prin migrate-bim (ALTER idempotent),
NU prin alembic upgrade (vezi CLAUDE.md - alembic desincronizat pe prod).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0024_issue_viewpoint'
down_revision: Union[str, Sequence[str], None] = '0023_clash_spatial_dedup'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('bim_issues', schema=None) as batch_op:
        batch_op.add_column(sa.Column('viewpoint_json', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('bim_issues', schema=None) as batch_op:
        batch_op.drop_column('viewpoint_json')
