"""cash on delivery setting

Réglage admin du paiement à la livraison — fermé : seuls le paiement en ligne
et NdjouriBank restent proposés aux nouvelles commandes.

Revision ID: f5c1a7e3b9d2
Revises: e2b6d9a4c7f1
Create Date: 2026-09-29 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f5c1a7e3b9d2'
down_revision: Union[str, None] = 'e2b6d9a4c7f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'payment_settings',
        sa.Column('cash_on_delivery_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('payment_settings', 'cash_on_delivery_enabled')
