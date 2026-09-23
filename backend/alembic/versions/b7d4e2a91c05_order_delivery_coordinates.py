"""order delivery coordinates

Revision ID: b7d4e2a91c05
Revises: 7380eedf17e1
Create Date: 2026-09-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d4e2a91c05'
down_revision: Union[str, None] = '7380eedf17e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('delivery_latitude', sa.Float(), nullable=True))
    op.add_column('orders', sa.Column('delivery_longitude', sa.Float(), nullable=True))
    # Rattrapage des commandes en point de retrait : la position du point est
    # connue. Celles à domicile d'avant cette migration restent sans position
    # (elle n'était pas conservée).
    op.execute(
        """
        UPDATE orders SET delivery_latitude = p.latitude, delivery_longitude = p.longitude
        FROM pickup_points p
        WHERE orders.pickup_point_id = p.id
        """
    )


def downgrade() -> None:
    op.drop_column('orders', 'delivery_longitude')
    op.drop_column('orders', 'delivery_latitude')
