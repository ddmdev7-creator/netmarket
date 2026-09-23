"""opaque handoff codes

QR de remise opaques et tournants (app/orders/handoff.py) : remplace le
jeton signé lisible par un code sans information, recalculé toutes les
60 s à partir d'un nombre aléatoire propre à l'étape.

Revision ID: e5b9c3d1a7f2
Revises: d8a2f5c7e913
Create Date: 2026-09-23 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5b9c3d1a7f2'
down_revision: Union[str, None] = 'd8a2f5c7e913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sub_orders', sa.Column('handoff_nonce', sa.String(length=64), nullable=True))
    op.add_column('sub_orders', sa.Column('handoff_stage', sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column('sub_orders', 'handoff_stage')
    op.drop_column('sub_orders', 'handoff_nonce')
