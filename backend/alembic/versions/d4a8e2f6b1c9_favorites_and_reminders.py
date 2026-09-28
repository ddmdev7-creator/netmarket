"""favorites and reminders

Favoris acheteur, alertes prix/stock (notifications liées à un produit) et
rappel de panier en attente.

Revision ID: d4a8e2f6b1c9
Revises: c7f3a1e9d4b2
Create Date: 2026-09-28 22:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4a8e2f6b1c9'
down_revision: Union[str, None] = 'c7f3a1e9d4b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'favorites',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('product_id', sa.UUID(), nullable=False),
        sa.Column('price_at_add', sa.Integer(), nullable=False),
        sa.Column('alerted_price', sa.Integer(), nullable=False),
        sa.Column('back_in_stock_alerted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'product_id', name='uq_favorites_user_product'),
    )
    op.create_index('ix_favorites_user_id', 'favorites', ['user_id'])
    op.create_index('ix_favorites_product_id', 'favorites', ['product_id'])

    op.add_column('notifications', sa.Column('product_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_notifications_product_id', 'notifications', 'products', ['product_id'], ['id'], ondelete='CASCADE'
    )
    op.add_column('users', sa.Column('cart_reminder_sent_at', sa.DateTime(timezone=True), nullable=True))

    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'favorite_price_drop'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'favorite_back_in_stock'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'cart_reminder'")


def downgrade() -> None:
    op.drop_column('users', 'cart_reminder_sent_at')
    op.drop_constraint('fk_notifications_product_id', 'notifications', type_='foreignkey')
    op.drop_column('notifications', 'product_id')
    op.drop_index('ix_favorites_product_id', table_name='favorites')
    op.drop_index('ix_favorites_user_id', table_name='favorites')
    op.drop_table('favorites')
