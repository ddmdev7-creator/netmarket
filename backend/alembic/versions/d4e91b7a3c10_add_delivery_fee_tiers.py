"""add delivery fee tiers and sub_orders.delivery_fee

Grille de paliers de distance (éditable par l'admin) et frais de livraison
figés par sous-commande au checkout. Les commandes existantes gardent 0.

Revision ID: d4e91b7a3c10
Revises: 524706130b04
Create Date: 2026-09-21 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4e91b7a3c10'
down_revision: Union[str, None] = '524706130b04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'delivery_fee_tiers',
        sa.Column('max_km', sa.Float(), nullable=True),
        sa.Column('fee', sa.Integer(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('fee >= 0', name='ck_delivery_fee_tiers_fee_non_negative'),
        sa.CheckConstraint('max_km IS NULL OR max_km > 0', name='ck_delivery_fee_tiers_max_km_positive'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('uq_delivery_fee_tiers_max_km', 'delivery_fee_tiers', ['max_km'], unique=True)
    op.create_index(
        'uq_delivery_fee_tiers_catch_all',
        'delivery_fee_tiers',
        ['max_km'],
        unique=True,
        postgresql_where=sa.text('max_km IS NULL'),
    )
    op.add_column('sub_orders', sa.Column('delivery_fee', sa.Integer(), server_default='0', nullable=False))
    op.create_check_constraint('ck_sub_orders_delivery_fee_non_negative', 'sub_orders', 'delivery_fee >= 0')


def downgrade() -> None:
    op.drop_constraint('ck_sub_orders_delivery_fee_non_negative', 'sub_orders', type_='check')
    op.drop_column('sub_orders', 'delivery_fee')
    op.drop_index('uq_delivery_fee_tiers_catch_all', table_name='delivery_fee_tiers')
    op.drop_index('uq_delivery_fee_tiers_max_km', table_name='delivery_fee_tiers')
    op.drop_table('delivery_fee_tiers')
