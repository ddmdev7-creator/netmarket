"""ledger wallets withdrawals

Grand livre à double entrée (app/wallets) : comptes, transactions,
écritures, demandes de retrait, et les réglages de répartition des gains
(part livreur, rémunération des points de retrait, délai de sécurité,
frais et minimum de retrait) sur payment_settings.

Aucune reprise d'historique : seules les commandes livrées à partir de
maintenant alimentent les soldes (un paiement confirmé avant cette
migration est rattrapé automatiquement à la livraison, voir
app/wallets/service.py::settle_sub_order).

Revision ID: c4f1a8e2d6b3
Revises: b7d4e2a91c05
Create Date: 2026-09-23 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c4f1a8e2d6b3'
down_revision: Union[str, None] = 'b7d4e2a91c05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

account_kind = postgresql.ENUM(
    'djomy_treasury', 'order_escrow', 'platform_revenue', 'withdrawals_pending', 'vendor', 'courier', 'pickup_point',
    name='ledger_account_kind', create_type=False,
)
payout_provider = postgresql.ENUM('OM', 'MOMO', 'PAYCARD', 'SOUTRA_MONEY', 'KULU', name='payout_provider', create_type=False)
transaction_kind = postgresql.ENUM(
    'payment_captured', 'sub_order_settled', 'refund_completed', 'withdrawal_requested', 'withdrawal_reversed',
    'withdrawal_paid',
    name='ledger_transaction_kind', create_type=False,
)
withdrawal_status = postgresql.ENUM(
    'pending', 'processing', 'paid', 'rejected', 'cancelled', 'failed', name='withdrawal_status', create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in (account_kind, payout_provider, transaction_kind, withdrawal_status):
        enum.create(bind, checkfirst=True)

    op.create_table(
        'ledger_accounts',
        sa.Column('kind', account_kind, nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=True),
        sa.Column('payout_provider', payout_provider, nullable=True),
        sa.Column('payout_account_number', sa.String(length=30), nullable=True),
        sa.Column('payout_beneficiary_name', sa.String(length=150), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('kind', 'owner_id', name='uq_ledger_accounts_kind_owner', postgresql_nulls_not_distinct=True),
    )

    op.create_table(
        'ledger_transactions',
        sa.Column('kind', transaction_kind, nullable=False),
        sa.Column('idempotency_key', sa.String(length=120), nullable=False),
        sa.Column('description', sa.String(length=300), nullable=False),
        sa.Column('order_id', sa.UUID(), nullable=True),
        sa.Column('sub_order_id', sa.UUID(), nullable=True),
        sa.Column('withdrawal_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key'),
    )
    op.create_index('ix_ledger_transactions_order_id', 'ledger_transactions', ['order_id'])

    op.create_table(
        'ledger_entries',
        sa.Column('transaction_id', sa.UUID(), nullable=False),
        sa.Column('account_id', sa.UUID(), nullable=False),
        sa.Column('amount', sa.BigInteger(), nullable=False),
        sa.Column('available_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['transaction_id'], ['ledger_transactions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['ledger_accounts.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ledger_entries_transaction_id', 'ledger_entries', ['transaction_id'])
    op.create_index('ix_ledger_entries_account_available', 'ledger_entries', ['account_id', 'available_at'])

    op.create_table(
        'withdrawals',
        sa.Column('account_id', sa.UUID(), nullable=False),
        sa.Column('requested_by', sa.UUID(), nullable=False),
        sa.Column('status', withdrawal_status, nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('fee', sa.Integer(), nullable=False),
        sa.Column('net_amount', sa.Integer(), nullable=False),
        sa.Column('fee_percent', sa.Numeric(5, 2), nullable=False),
        sa.Column('payout_provider', payout_provider, nullable=False),
        sa.Column('payout_account_number', sa.String(length=30), nullable=False),
        sa.Column('payout_beneficiary_name', sa.String(length=150), nullable=False),
        sa.Column('djomy_order_id', sa.String(length=100), nullable=True),
        sa.Column('djomy_payout_id', sa.String(length=100), nullable=True),
        sa.Column('djomy_total_amount', sa.Integer(), nullable=True),
        sa.Column('admin_note', sa.String(length=300), nullable=True),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['ledger_accounts.id']),
        sa.ForeignKeyConstraint(['requested_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_withdrawals_account_id', 'withdrawals', ['account_id'])
    op.create_index('ix_withdrawals_djomy_payout_id', 'withdrawals', ['djomy_payout_id'])

    op.add_column('payment_settings', sa.Column('courier_delivery_share_percent', sa.Integer(), server_default='80', nullable=False))
    op.add_column('payment_settings', sa.Column('pickup_point_fee_per_parcel', sa.Integer(), server_default='2000', nullable=False))
    op.add_column('payment_settings', sa.Column('earnings_hold_days', sa.Integer(), server_default='3', nullable=False))
    op.add_column('payment_settings', sa.Column('withdrawal_fee_percent', sa.Numeric(5, 2), server_default='0', nullable=False))
    op.add_column('payment_settings', sa.Column('min_withdrawal_amount', sa.Integer(), server_default='10000', nullable=False))


def downgrade() -> None:
    for column in (
        'min_withdrawal_amount', 'withdrawal_fee_percent', 'earnings_hold_days', 'pickup_point_fee_per_parcel',
        'courier_delivery_share_percent',
    ):
        op.drop_column('payment_settings', column)
    op.drop_table('withdrawals')
    op.drop_table('ledger_entries')
    op.drop_table('ledger_transactions')
    op.drop_table('ledger_accounts')
    bind = op.get_bind()
    for enum in (withdrawal_status, transaction_kind, payout_provider, account_kind):
        enum.drop(bind, checkfirst=True)
