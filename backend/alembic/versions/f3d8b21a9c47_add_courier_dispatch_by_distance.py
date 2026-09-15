"""add courier dispatch by distance

Revision ID: f3d8b21a9c47
Revises: a1c4f7e2b8d3
Create Date: 2026-09-15 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f3d8b21a9c47'
down_revision: Union[str, None] = 'a1c4f7e2b8d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'delivery_request'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'delivery_request_accepted'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'delivery_no_courier_found'")

    op.add_column('vendors', sa.Column('latitude', sa.Float(), nullable=True))
    op.add_column('vendors', sa.Column('longitude', sa.Float(), nullable=True))

    op.add_column('couriers', sa.Column('latitude', sa.Float(), nullable=True))
    op.add_column('couriers', sa.Column('longitude', sa.Float(), nullable=True))
    op.add_column(
        'couriers',
        sa.Column('is_online', sa.Boolean(), nullable=False, server_default='false'),
    )

    op.add_column(
        'sub_orders',
        sa.Column('dispatch_offered_courier_id', sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        'fk_sub_orders_dispatch_offered_courier_id_couriers',
        'sub_orders', 'couriers',
        ['dispatch_offered_courier_id'], ['id'],
    )
    op.add_column(
        'sub_orders',
        sa.Column('dispatch_queue', postgresql.ARRAY(sa.UUID()), nullable=False, server_default='{}'),
    )

    op.add_column('notifications', sa.Column('sub_order_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_notifications_sub_order_id_sub_orders',
        'notifications', 'sub_orders',
        ['sub_order_id'], ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint('fk_notifications_sub_order_id_sub_orders', 'notifications', type_='foreignkey')
    op.drop_column('notifications', 'sub_order_id')

    op.drop_column('sub_orders', 'dispatch_queue')
    op.drop_constraint('fk_sub_orders_dispatch_offered_courier_id_couriers', 'sub_orders', type_='foreignkey')
    op.drop_column('sub_orders', 'dispatch_offered_courier_id')

    op.drop_column('couriers', 'is_online')
    op.drop_column('couriers', 'longitude')
    op.drop_column('couriers', 'latitude')

    op.drop_column('vendors', 'longitude')
    op.drop_column('vendors', 'latitude')
    # Les nouvelles valeurs d'enum restent (pas de "DROP VALUE" en Postgres),
    # même choix que les migrations précédentes de ce type.
