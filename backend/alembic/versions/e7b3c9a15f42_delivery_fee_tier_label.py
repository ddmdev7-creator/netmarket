"""delivery fee tier label

Libellé optionnel (zone couverte) sur les paliers de frais de livraison, pour
que l'admin s'y retrouve — informatif uniquement, le calcul ne dépend que de
max_km.

Revision ID: e7b3c9a15f42
Revises: d4e91b7a3c10
Create Date: 2026-09-21 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e7b3c9a15f42'
down_revision: Union[str, None] = 'd4e91b7a3c10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('delivery_fee_tiers', sa.Column('label', sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column('delivery_fee_tiers', 'label')
