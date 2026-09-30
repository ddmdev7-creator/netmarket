"""Abonnements : quotas par formule, formule Gratuit, essais, usage IA, réglages

Revision ID: c5a2e8f4d1b7
Revises: b3e9f1a7c5d2
Create Date: 2026-09-30
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "c5a2e8f4d1b7"
down_revision: str | None = "b3e9f1a7c5d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("subscription_plans", sa.Column("is_free", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("subscription_plans", sa.Column("description", sa.String(length=300), nullable=True))
    op.add_column("subscription_plans", sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False))
    op.add_column("subscription_plans", sa.Column("max_products", sa.Integer(), nullable=True))
    op.add_column(
        "subscription_plans", sa.Column("max_images_per_product", sa.Integer(), server_default="4", nullable=False)
    )
    op.add_column(
        "subscription_plans", sa.Column("ai_enhancements_per_month", sa.Integer(), server_default="0", nullable=True)
    )
    op.add_column("subscription_plans", sa.Column("featured_per_month", sa.Integer(), server_default="0", nullable=False))
    op.add_column(
        "subscription_plans", sa.Column("commission_discount", sa.Numeric(5, 2), server_default="0", nullable=False)
    )

    op.add_column("vendor_subscriptions", sa.Column("is_trial", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("vendor_subscriptions", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("vendor_subscriptions", sa.Column("cancel_reason", sa.String(length=300), nullable=True))
    op.add_column("vendor_subscriptions", sa.Column("last_reminder_days", sa.Integer(), nullable=True))
    op.add_column("vendor_subscriptions", sa.Column("grace_processed_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "subscription_usage",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_id", UUID(as_uuid=True), sa.ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_subscription_usage_vendor_kind_created", "subscription_usage", ["vendor_id", "kind", "created_at"]
    )

    op.create_table(
        "subscription_settings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("auto_trial_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "auto_trial_plan_id",
            UUID(as_uuid=True),
            sa.ForeignKey("subscription_plans.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("auto_trial_days", sa.Integer(), server_default="14", nullable=False),
        sa.Column("grace_days", sa.Integer(), server_default="7", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'subscription_reminder'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'subscription_update'")

    # Formules validées le 2026-09-30 : l'offre payante existante devient « Pro »,
    # « Gratuit » porte les quotas de base, « Business » est créée hors vente
    # (l'admin fixe son prix puis l'active).
    op.execute(
        """
        UPDATE subscription_plans SET
            name = CASE WHEN name = 'Premium mensuel' THEN 'Pro' ELSE name END,
            description = 'Pour les boutiques qui grandissent : plus de produits, photos pro et commission réduite.',
            sort_order = 1, max_products = 150, max_images_per_product = 8,
            ai_enhancements_per_month = 100, featured_per_month = 3, commission_discount = 2
        WHERE is_free = false
        """
    )
    plans = sa.table(
        "subscription_plans",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("price_gnf", sa.Integer),
        sa.column("duration_days", sa.Integer),
        sa.column("is_active", sa.Boolean),
        sa.column("is_free", sa.Boolean),
        sa.column("description", sa.String),
        sa.column("sort_order", sa.Integer),
        sa.column("max_products", sa.Integer),
        sa.column("max_images_per_product", sa.Integer),
        sa.column("ai_enhancements_per_month", sa.Integer),
        sa.column("featured_per_month", sa.Integer),
        sa.column("commission_discount", sa.Numeric),
    )
    op.bulk_insert(
        plans,
        [
            {
                "id": uuid.uuid4(),
                "name": "Gratuit",
                "price_gnf": 0,
                "duration_days": 0,
                "is_active": True,
                "is_free": True,
                "description": "Pour démarrer : l'essentiel pour vendre sur NdjouriMarket.",
                "sort_order": 0,
                "max_products": 15,
                "max_images_per_product": 4,
                "ai_enhancements_per_month": 3,
                "featured_per_month": 0,
                "commission_discount": 0,
            },
            {
                "id": uuid.uuid4(),
                "name": "Business",
                "price_gnf": 60000,
                "duration_days": 30,
                "is_active": False,
                "is_free": False,
                "description": "Pour les grandes boutiques : produits illimités et la commission la plus basse.",
                "sort_order": 2,
                "max_products": None,
                "max_images_per_product": 12,
                "ai_enhancements_per_month": 500,
                "featured_per_month": 10,
                "commission_discount": 4,
            },
        ],
    )
    op.execute(f"INSERT INTO subscription_settings (id) VALUES ('{uuid.uuid4()}')")


def downgrade() -> None:
    op.drop_table("subscription_settings")
    op.drop_index("ix_subscription_usage_vendor_kind_created", table_name="subscription_usage")
    op.drop_table("subscription_usage")
    op.execute(
        "DELETE FROM subscription_plans WHERE is_free OR (name = 'Business' AND id NOT IN (SELECT plan_id FROM vendor_subscriptions))"
    )
    for column in ("grace_processed_at", "last_reminder_days", "cancel_reason", "cancelled_at", "is_trial"):
        op.drop_column("vendor_subscriptions", column)
    for column in (
        "commission_discount",
        "featured_per_month",
        "ai_enhancements_per_month",
        "max_images_per_product",
        "max_products",
        "sort_order",
        "description",
        "is_free",
    ):
        op.drop_column("subscription_plans", column)
