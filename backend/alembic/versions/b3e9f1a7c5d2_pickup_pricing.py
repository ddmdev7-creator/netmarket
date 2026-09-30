"""Tarif de livraison en point de retrait (grille dédiée ou pourcentage) +
plafonds du retrait offert par le vendeur

Revision ID: b3e9f1a7c5d2
Revises: a8d4c2e6f1b3
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3e9f1a7c5d2"
down_revision: str | None = "a8d4c2e6f1b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "delivery_fee_tiers", sa.Column("kind", sa.String(length=16), server_default="home", nullable=False)
    )
    # Les unicités deviennent propres à chaque grille.
    op.drop_index("uq_delivery_fee_tiers_max_km", table_name="delivery_fee_tiers")
    op.drop_index("uq_delivery_fee_tiers_catch_all", table_name="delivery_fee_tiers")
    op.drop_index("uq_delivery_fee_tiers_default", table_name="delivery_fee_tiers")
    op.create_index("uq_delivery_fee_tiers_max_km", "delivery_fee_tiers", ["kind", "max_km"], unique=True)
    op.create_index(
        "uq_delivery_fee_tiers_catch_all",
        "delivery_fee_tiers",
        ["kind"],
        unique=True,
        postgresql_where=sa.text("max_km IS NULL"),
    )
    op.create_index(
        "uq_delivery_fee_tiers_default",
        "delivery_fee_tiers",
        ["kind"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )

    op.add_column(
        "payment_settings",
        sa.Column("pickup_pricing_mode", sa.String(length=16), server_default="percent", nullable=False),
    )
    op.add_column("payment_settings", sa.Column("pickup_fee_percent", sa.Integer(), server_default="100", nullable=False))

    op.add_column("vendors", sa.Column("pickup_offer_max_amount", sa.Integer(), nullable=True))
    op.add_column("vendors", sa.Column("pickup_offer_max_km", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("vendors", "pickup_offer_max_km")
    op.drop_column("vendors", "pickup_offer_max_amount")
    op.drop_column("payment_settings", "pickup_fee_percent")
    op.drop_column("payment_settings", "pickup_pricing_mode")

    op.execute("DELETE FROM delivery_fee_tiers WHERE kind <> 'home'")
    op.drop_index("uq_delivery_fee_tiers_default", table_name="delivery_fee_tiers")
    op.drop_index("uq_delivery_fee_tiers_catch_all", table_name="delivery_fee_tiers")
    op.drop_index("uq_delivery_fee_tiers_max_km", table_name="delivery_fee_tiers")
    op.create_index("uq_delivery_fee_tiers_max_km", "delivery_fee_tiers", ["max_km"], unique=True)
    op.create_index(
        "uq_delivery_fee_tiers_catch_all",
        "delivery_fee_tiers",
        ["max_km"],
        unique=True,
        postgresql_where=sa.text("max_km IS NULL"),
    )
    op.create_index(
        "uq_delivery_fee_tiers_default",
        "delivery_fee_tiers",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.drop_column("delivery_fee_tiers", "kind")
