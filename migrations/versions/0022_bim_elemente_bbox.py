"""0022 bim_elemente bbox

Revision ID: 0022_bim_elemente_bbox
Revises: 0021_gantt_calendar
Create Date: 2026-06-13 00:00:00.000000

Faza 2 BIM: extragere Property Sets + bounding box la importul IFC.
Coloana proprietati_json exista deja pe bim_elemente; aici adaugam doar
bbox_json (TEXT) + bbox_sursa (VARCHAR(20)), ambele NULLABLE.
Strict aditiv - pe prod se aplica prin migrate-bim (ALTER idempotent) sau
db.create_all() + alembic stamp head (NU alembic upgrade).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0022_bim_elemente_bbox'
down_revision: Union[str, Sequence[str], None] = '0021_gantt_calendar'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('bim_elemente', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bbox_json', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('bbox_sursa', sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('bim_elemente', schema=None) as batch_op:
        batch_op.drop_column('bbox_sursa')
        batch_op.drop_column('bbox_json')
