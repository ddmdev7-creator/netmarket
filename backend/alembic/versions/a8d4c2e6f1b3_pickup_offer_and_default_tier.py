"""Retrait offert par le vendeur + palier de livraison par défaut

Revision ID: a8d4c2e6f1b3
Revises: f5c1a7e3b9d2
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a8d4c2e6f1b3"
down_revision: str | None = "f5c1a7e3b9d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("vendors", sa.Column("offers_pickup_delivery", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("vendors", sa.Column("pickup_offer_min_amount", sa.Integer(), server_default="0", nullable=False))
    op.add_column("sub_orders", sa.Column("vendor_delivery_fee", sa.Integer(), server_default="0", nullable=False))
    op.create_check_constraint("ck_sub_orders_vendor_delivery_fee_non_negative", "sub_orders", "vendor_delivery_fee >= 0")
    op.add_column("delivery_fee_tiers", sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False))
    op.create_index(
        "uq_delivery_fee_tiers_default",
        "delivery_fee_tiers",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )


def downgrade() -> None:
    op.drop_index("uq_delivery_fee_tiers_default", table_name="delivery_fee_tiers")
    op.drop_column("delivery_fee_tiers", "is_default")
    op.drop_constraint("ck_sub_orders_vendor_delivery_fee_non_negative", "sub_orders", type_="check")
    op.drop_column("sub_orders", "vendor_delivery_fee")
    op.drop_column("vendors", "pickup_offer_min_amount")
    op.drop_column("vendors", "offers_pickup_delivery")
