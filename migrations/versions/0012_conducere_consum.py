"""0012 conducere consum (calculator consum combustibil masini)

Revision ID: 0012_conducere_consum
Revises: 0011_deviz_pricing
Create Date: 2026-05-24 10:00:00.000000

Adauga pe conduceri_masini campurile pentru calculatorul de consum:
  - distanta_km            : distanta calculata pe harta (Mapbox Directions)
  - combustibil_consumat   : litri consumati = consum_mediu x km / 100
  - waypoints_json         : JSON cu punctele A/B/C/D ale rutei

Strict aditiv, backward compatible (toate coloanele nullable).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0012_conducere_consum'
down_revision: Union[str, Sequence[str], None] = '0011_deviz_pricing'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('conduceri_masini', schema=None) as batch_op:
        batch_op.add_column(sa.Column('distanta_km', sa.Numeric(precision=7, scale=2), nullable=True))
        batch_op.add_column(sa.Column('combustibil_consumat', sa.Numeric(precision=7, scale=2), nullable=True))
        batch_op.add_column(sa.Column('waypoints_json', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('conduceri_masini', schema=None) as batch_op:
        batch_op.drop_column('waypoints_json')
        batch_op.drop_column('combustibil_consumat')
        batch_op.drop_column('distanta_km')
