"""Taille de colis S/M/L/XL : produit, sous-commande, rémunération du point
de retrait par taille, garde prolongée, bonus volume, supplément L/XL

Revision ID: d7b3f9a2e6c4
Revises: c5a2e8f4d1b7
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7b3f9a2e6c4"
down_revision: str | None = "c5a2e8f4d1b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SETTINGS = {
    "pickup_fee_m": 2500,
    "pickup_fee_l": 4000,
    "pickup_fee_xl": 6000,
    "pickup_storage_free_days": 3,
    "pickup_storage_fee_per_day": 200,
    "pickup_storage_max_days": 7,
    "pickup_volume_bonus_threshold": 100,
    "pickup_volume_bonus_percent": 10,
    "pickup_return_percent": 50,
    "delivery_surcharge_l": 5000,
    "delivery_surcharge_xl": 10000,
}


def upgrade() -> None:
    op.add_column("products", sa.Column("parcel_size", sa.String(length=2), server_default="S", nullable=False))
    op.add_column("sub_orders", sa.Column("parcel_size", sa.String(length=2), server_default="S", nullable=False))
    op.add_column(
        "sub_orders", sa.Column("declared_parcel_size", sa.String(length=2), server_default="S", nullable=False)
    )
    op.add_column("sub_orders", sa.Column("size_surcharge", sa.Integer(), server_default="0", nullable=False))
    for name, default in _SETTINGS.items():
        op.add_column("payment_settings", sa.Column(name, sa.Integer(), server_default=str(default), nullable=False))
    # Le forfait existant (réglé par l'admin) devient le tarif S, inchangé.


def downgrade() -> None:
    for name in _SETTINGS:
        op.drop_column("payment_settings", name)
    op.drop_column("sub_orders", "size_surcharge")
    op.drop_column("sub_orders", "declared_parcel_size")
    op.drop_column("sub_orders", "parcel_size")
    op.drop_column("products", "parcel_size")
