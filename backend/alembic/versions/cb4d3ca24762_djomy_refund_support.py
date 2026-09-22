"""djomy refund support

Remboursement automatique d'un paiement en ligne annulé avant traitement
vendeur (voir app/orders/service.py::cancel_order) : nouveaux statuts de
paiement, référence du payout de remboursement, et un réglage admin pour le
délai de remboursement affiché à l'acheteur.

Revision ID: cb4d3ca24762
Revises: eae236b840d0
Create Date: 2026-09-22 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'cb4d3ca24762'
down_revision: Union[str, None] = 'eae236b840d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE payment_status ADD VALUE IF NOT EXISTS 'refund_pending'")
    op.execute("ALTER TYPE payment_status ADD VALUE IF NOT EXISTS 'refunded'")
    op.execute("ALTER TYPE payment_status ADD VALUE IF NOT EXISTS 'refund_failed'")

    op.add_column('payments', sa.Column('refund_reference', sa.String(length=200), nullable=True))

    op.create_table(
        'payment_settings',
        sa.Column('refund_delay_hours', sa.Integer(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    # Une seule ligne, toujours — voir app/payments/repository.py::get_settings.
    op.execute("INSERT INTO payment_settings (id, refund_delay_hours) VALUES (gen_random_uuid(), 48)")


def downgrade() -> None:
    op.drop_table('payment_settings')
    op.drop_column('payments', 'refund_reference')
    # Pas de retrait des valeurs d'enum (voir eae236b840d0) — inerte si inutilisée.
