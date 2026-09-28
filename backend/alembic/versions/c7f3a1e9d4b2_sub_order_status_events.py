"""sub order status events

Historique horodaté des statuts de sous-commande (frise de suivi acheteur).
Les sous-commandes existantes reçoivent un événement "pending" à leur date
de création, plus leur statut actuel à leur dernière mise à jour.

Revision ID: c7f3a1e9d4b2
Revises: b1e7c4d9a2f6
Create Date: 2026-09-28 20:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c7f3a1e9d4b2'
down_revision: Union[str, None] = 'b1e7c4d9a2f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    order_status = postgresql.ENUM(name='order_status', create_type=False)
    op.create_table(
        'sub_order_status_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('sub_order_id', sa.UUID(), nullable=False),
        sa.Column('status', order_status, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['sub_order_id'], ['sub_orders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sub_order_status_events_sub_order_id', 'sub_order_status_events', ['sub_order_id'])
    op.execute(
        """
        INSERT INTO sub_order_status_events (id, sub_order_id, status, created_at, updated_at)
        SELECT gen_random_uuid(), id, 'pending', created_at, created_at FROM sub_orders
        """
    )
    op.execute(
        """
        INSERT INTO sub_order_status_events (id, sub_order_id, status, created_at, updated_at)
        SELECT gen_random_uuid(), id, status, updated_at, updated_at FROM sub_orders WHERE status <> 'pending'
        """
    )


def downgrade() -> None:
    op.drop_index('ix_sub_order_status_events_sub_order_id', table_name='sub_order_status_events')
    op.drop_table('sub_order_status_events')
