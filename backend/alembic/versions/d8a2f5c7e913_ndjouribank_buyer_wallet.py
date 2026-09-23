"""ndjouribank buyer wallet

Phase 3 du chantier comptes : solde NdjouriBank des acheteurs (recharge via
Djomy, paiement des commandes avec le solde, remboursements crédités sur le
solde). Désactivé par défaut (payment_settings.buyer_wallet_enabled) tant
que la conformité n'est pas validée.

Revision ID: d8a2f5c7e913
Revises: c4f1a8e2d6b3
Create Date: 2026-09-23 16:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd8a2f5c7e913'
down_revision: Union[str, None] = 'c4f1a8e2d6b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

topup_status = postgresql.ENUM('pending', 'paid', 'failed', 'cancelled', name='wallet_topup_status', create_type=False)


def upgrade() -> None:
    op.execute("ALTER TYPE payment_method ADD VALUE IF NOT EXISTS 'wallet'")
    op.execute("ALTER TYPE ledger_account_kind ADD VALUE IF NOT EXISTS 'buyer'")
    for value in ('wallet_topup', 'wallet_payment', 'refund_to_wallet'):
        op.execute(f"ALTER TYPE ledger_transaction_kind ADD VALUE IF NOT EXISTS '{value}'")

    topup_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        'wallet_topups',
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('status', topup_status, nullable=False),
        sa.Column('payer_phone', sa.String(length=20), nullable=False),
        sa.Column('provider_reference', sa.String(length=200), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_wallet_topups_user_id', 'wallet_topups', ['user_id'])

    op.add_column('payment_settings', sa.Column('buyer_wallet_enabled', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column('payment_settings', sa.Column('wallet_topup_min', sa.Integer(), server_default='5000', nullable=False))
    op.add_column('payment_settings', sa.Column('wallet_topup_max', sa.Integer(), server_default='2000000', nullable=False))
    op.add_column('payment_settings', sa.Column('wallet_max_balance', sa.Integer(), server_default='5000000', nullable=False))


def downgrade() -> None:
    # Les valeurs ajoutées aux types enum PostgreSQL ne se retirent pas.
    for column in ('wallet_max_balance', 'wallet_topup_max', 'wallet_topup_min', 'buyer_wallet_enabled'):
        op.drop_column('payment_settings', column)
    op.drop_table('wallet_topups')
    topup_status.drop(op.get_bind(), checkfirst=True)
