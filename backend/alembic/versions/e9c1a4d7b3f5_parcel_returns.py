"""Retour des colis non retirés au point de retrait

Revision ID: e9c1a4d7b3f5
Revises: d7b3f9a2e6c4
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "e9c1a4d7b3f5"
down_revision: str | None = "d7b3f9a2e6c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for value in ("return_pending", "returning", "returned"):
        op.execute(f"ALTER TYPE order_status ADD VALUE IF NOT EXISTS '{value}'")
    op.execute("ALTER TYPE ledger_transaction_kind ADD VALUE IF NOT EXISTS 'sub_order_returned'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'pickup_reminder'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'parcel_return'")

    op.add_column(
        "sub_orders",
        sa.Column("outbound_courier_id", UUID(as_uuid=True), sa.ForeignKey("couriers.id"), nullable=True),
    )
    op.add_column("sub_orders", sa.Column("return_fee", sa.Integer(), server_default="0", nullable=False))
    op.add_column("sub_orders", sa.Column("pickup_reminder_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    # Les valeurs d'enum Postgres ne se retirent pas : seules les colonnes partent.
    op.drop_column("sub_orders", "pickup_reminder_days")
    op.drop_column("sub_orders", "return_fee")
    op.drop_column("sub_orders", "outbound_courier_id")
