"""Schémas des portefeuilles (vendeur/livreur/point de retrait) et du compte principal admin."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.wallets.models import AccountKind, PayoutProvider, TransactionKind, WithdrawalStatus


class WalletBalance(BaseModel):
    """Vu du bénéficiaire : ce que la plateforme lui doit."""

    # Retirable maintenant.
    available: int
    # Gains dont le délai de sécurité n'est pas écoulé.
    pending: int
    total: int


class WalletRead(BaseModel):
    id: uuid.UUID
    kind: AccountKind
    owner_id: uuid.UUID | None
    owner_label: str
    balance: WalletBalance
    # Montant réservé par des retraits demandés ou en cours de versement
    # (déjà déduit du solde).
    withdrawals_in_progress: int
    payout_provider: PayoutProvider | None
    payout_account_number: str | None
    payout_beneficiary_name: str | None
    # Règles en vigueur, pour le formulaire de retrait.
    min_withdrawal_amount: int
    withdrawal_fee_percent: float
    earnings_hold_days: int


class WalletEntryRead(BaseModel):
    id: uuid.UUID
    created_at: datetime
    kind: TransactionKind
    description: str
    # Du point de vue du titulaire : > 0 argent reçu, < 0 argent sorti.
    amount: int
    available_at: datetime
    is_pending: bool
    order_id: uuid.UUID | None
    sub_order_id: uuid.UUID | None
    withdrawal_id: uuid.UUID | None


class PayoutMethodUpdate(BaseModel):
    payout_provider: PayoutProvider
    # Numéro local (ex. 622000000) : chiffres uniquement, sans indicatif.
    payout_account_number: str = Field(pattern=r"^\d{8,15}$")
    payout_beneficiary_name: str = Field(min_length=2, max_length=150)


class WithdrawalCreate(BaseModel):
    amount: int = Field(gt=0)


class WithdrawalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    status: WithdrawalStatus
    amount: int
    fee: int
    net_amount: int
    fee_percent: float
    payout_provider: PayoutProvider
    payout_account_number: str
    payout_beneficiary_name: str
    admin_note: str | None
    created_at: datetime
    processed_at: datetime | None


class AdminWithdrawalRead(WithdrawalRead):
    account_kind: AccountKind
    owner_label: str
    djomy_payout_id: str | None
    djomy_total_amount: int | None


class WithdrawalReject(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class AdminFinanceOverview(BaseModel):
    """Le compte principal : ce qui est chez Djomy, et à qui cela revient.
    treasury == escrow + beneficiaries_total + withdrawals_reserved + platform_revenue
    (vrai par construction, affiché comme contrôle de cohérence)."""

    treasury: int
    escrow: int
    beneficiaries_available: int
    beneficiaries_pending: int
    beneficiaries_total: int
    withdrawals_reserved: int
    platform_revenue: int
    is_balanced: bool
    # Cumuls depuis le début.
    total_captured: int
    total_refunded: int
    total_paid_out: int
    withdrawals_pending_count: int
    withdrawals_pending_amount: int
    withdrawals_processing_count: int
    withdrawals_processing_amount: int


class AdminWalletRead(BaseModel):
    id: uuid.UUID
    kind: AccountKind
    owner_id: uuid.UUID | None
    owner_label: str
    balance: WalletBalance
    withdrawals_in_progress: int
    payout_provider: PayoutProvider | None
    payout_account_number: str | None


class LedgerEntryLine(BaseModel):
    account_kind: AccountKind
    owner_label: str
    # Convention comptable brute : > 0 débit, < 0 crédit.
    amount: int


class LedgerTransactionRead(BaseModel):
    id: uuid.UUID
    created_at: datetime
    kind: TransactionKind
    description: str
    order_id: uuid.UUID | None
    sub_order_id: uuid.UUID | None
    withdrawal_id: uuid.UUID | None
    lines: list[LedgerEntryLine]


class EarningsSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    courier_delivery_share_percent: int
    pickup_point_fee_per_parcel: int
    earnings_hold_days: int
    withdrawal_fee_percent: float
    min_withdrawal_amount: int


class EarningsSettingsUpdate(BaseModel):
    courier_delivery_share_percent: int = Field(ge=0, le=100)
    pickup_point_fee_per_parcel: int = Field(ge=0, le=1_000_000)
    earnings_hold_days: int = Field(ge=0, le=60)
    withdrawal_fee_percent: float = Field(ge=0, le=20)
    min_withdrawal_amount: int = Field(ge=1000, le=100_000_000)
