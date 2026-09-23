"""Grand livre à double entrée : les soldes de tous les acteurs (vendeurs,
livreurs, points de retrait) et le « compte principal » de la plateforme.

Principe : chaque mouvement d'argent est une LedgerTransaction composée de
LedgerEntry dont la somme vaut toujours 0 (ce qui sort d'un compte entre
dans un autre). Aucun solde n'est stocké : il se calcule toujours à partir
des écritures (voir repository.balances), donc il ne peut pas dériver.

Convention de signe : `amount > 0` = débit, `amount < 0` = crédit. Le seul
compte « d'actif » est DJOMY_TREASURY (l'argent réellement détenu chez
Djomy, solde = somme des montants) ; tous les autres sont des comptes de
passif ou de produit (ce que la plateforme doit à quelqu'un, ou a gagné),
dont le solde affiché est l'opposé de la somme — voir service.balance_of.
L'égalité TRÉSORERIE = SÉQUESTRE + DÛ AUX ACTEURS + RETRAITS EN COURS +
REVENUS PLATEFORME est donc toujours vraie par construction.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


def _enum(enum_cls: type[StrEnum], name: str) -> SAEnum:
    return SAEnum(enum_cls, name=name, values_callable=lambda enum: [e.value for e in enum])


class AccountKind(StrEnum):
    # Actif : argent réellement détenu sur le compte marchand Djomy.
    DJOMY_TREASURY = "djomy_treasury"
    # Paiements en ligne capturés dont la commande n'est pas encore livrée
    # (ni remboursée) — l'argent est là, mais n'appartient encore à personne.
    ORDER_ESCROW = "order_escrow"
    # Commissions + marge sur les frais de livraison − rémunération des points
    # de retrait ± écart entre frais de retrait estimés et frais Djomy réels.
    PLATFORM_REVENUE = "platform_revenue"
    # Montants réservés par une demande de retrait, pas encore versés.
    WITHDRAWALS_PENDING = "withdrawals_pending"
    # Portefeuilles des bénéficiaires — owner_id = Vendor.id / Courier.id / PickupPoint.id.
    VENDOR = "vendor"
    COURIER = "courier"
    PICKUP_POINT = "pickup_point"


BENEFICIARY_KINDS = (AccountKind.VENDOR, AccountKind.COURIER, AccountKind.PICKUP_POINT)


class PayoutProvider(StrEnum):
    """Moyens de réception acceptés par l'API payout Djomy (providerCode)."""

    OM = "OM"
    MOMO = "MOMO"
    PAYCARD = "PAYCARD"
    SOUTRA_MONEY = "SOUTRA_MONEY"
    KULU = "KULU"


class LedgerAccount(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ledger_accounts"
    # Comptes système : owner_id NULL — NULLS NOT DISTINCT pour qu'il n'en
    # existe qu'un par type malgré tout.
    __table_args__ = (
        UniqueConstraint("kind", "owner_id", name="uq_ledger_accounts_kind_owner", postgresql_nulls_not_distinct=True),
    )

    kind: Mapped[AccountKind] = mapped_column(_enum(AccountKind, "ledger_account_kind"), nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    # Moyen de réception des retraits (bénéficiaires uniquement).
    payout_provider: Mapped[PayoutProvider | None] = mapped_column(
        _enum(PayoutProvider, "payout_provider"), nullable=True
    )
    payout_account_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    payout_beneficiary_name: Mapped[str | None] = mapped_column(String(150), nullable=True)


class TransactionKind(StrEnum):
    PAYMENT_CAPTURED = "payment_captured"
    SUB_ORDER_SETTLED = "sub_order_settled"
    REFUND_COMPLETED = "refund_completed"
    WITHDRAWAL_REQUESTED = "withdrawal_requested"
    # Retrait annulé par le bénéficiaire, refusé par l'admin ou échoué chez
    # Djomy : la réservation revient dans le portefeuille.
    WITHDRAWAL_REVERSED = "withdrawal_reversed"
    WITHDRAWAL_PAID = "withdrawal_paid"


class LedgerTransaction(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "ledger_transactions"

    kind: Mapped[TransactionKind] = mapped_column(_enum(TransactionKind, "ledger_transaction_kind"), nullable=False)
    # Clé métier unique (« capture:<order_id> », « settle:<sub_order_id> »…) :
    # un même événement (webhook rejoué, double clic) ne s'écrit jamais deux fois.
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    order_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    sub_order_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    withdrawal_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    entries: Mapped[list["LedgerEntry"]] = relationship(back_populates="transaction", cascade="all, delete-orphan")


class LedgerEntry(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "ledger_entries"
    __table_args__ = (Index("ix_ledger_entries_account_available", "account_id", "available_at"),)

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("ledger_transactions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("ledger_accounts.id"), nullable=False
    )
    # > 0 débit, < 0 crédit (voir docstring du module). BigInteger : en GNF,
    # les cumuls de la trésorerie dépassent vite 2^31.
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Un crédit de gain n'est retirable qu'à partir de cette date (délai de
    # sécurité réglable, voir PaymentSettings.earnings_hold_days) ; les autres
    # écritures sont disponibles immédiatement.
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    transaction: Mapped[LedgerTransaction] = relationship(back_populates="entries")


class WithdrawalStatus(StrEnum):
    PENDING = "pending"  # demandé, en attente de validation admin
    PROCESSING = "processing"  # validé, versement Djomy en cours
    PAID = "paid"
    REJECTED = "rejected"
    CANCELLED = "cancelled"  # annulé par le bénéficiaire avant validation
    FAILED = "failed"  # rejeté/échoué côté Djomy


class Withdrawal(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "withdrawals"

    account_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("ledger_accounts.id"), nullable=False, index=True
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status: Mapped[WithdrawalStatus] = mapped_column(
        _enum(WithdrawalStatus, "withdrawal_status"), default=WithdrawalStatus.PENDING, nullable=False
    )
    # Débité du portefeuille = fee (frais estimés, à la charge du bénéficiaire)
    # + net_amount (réellement envoyé via Djomy).
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    fee: Mapped[int] = mapped_column(Integer, nullable=False)
    net_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    fee_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    # Destination figée au moment de la demande.
    payout_provider: Mapped[PayoutProvider] = mapped_column(_enum(PayoutProvider, "payout_provider"), nullable=False)
    payout_account_number: Mapped[str] = mapped_column(String(30), nullable=False)
    payout_beneficiary_name: Mapped[str] = mapped_column(String(150), nullable=False)
    djomy_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    djomy_payout_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    # Montant réellement débité du compte marchand Djomy (net + frais Djomy).
    djomy_total_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    admin_note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
