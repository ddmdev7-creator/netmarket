"""Accès base du grand livre : comptes, écritures, soldes, retraits."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.pagination import PageParams
from app.wallets.models import (
    AccountKind,
    LedgerAccount,
    LedgerEntry,
    LedgerTransaction,
    TransactionKind,
    WalletTopUp,
    Withdrawal,
    WithdrawalStatus,
)


async def get_or_create_account(
    db: AsyncSession, kind: AccountKind, owner_id: uuid.UUID | None = None, *, for_update: bool = False
) -> LedgerAccount:
    """INSERT … ON CONFLICT DO NOTHING puis SELECT : deux requêtes
    concurrentes (deux livraisons simultanées) ne créent jamais deux fois le
    même compte. `for_update` verrouille la ligne jusqu'à la fin de la
    transaction — sert de verrou pour les retraits (voir service)."""
    await db.execute(
        insert(LedgerAccount)
        .values(id=uuid.uuid4(), kind=kind, owner_id=owner_id)
        .on_conflict_do_nothing(constraint="uq_ledger_accounts_kind_owner")
    )
    owner_filter = LedgerAccount.owner_id.is_(None) if owner_id is None else LedgerAccount.owner_id == owner_id
    stmt = select(LedgerAccount).where(LedgerAccount.kind == kind, owner_filter)
    if for_update:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one()


async def get_account(db: AsyncSession, account_id: uuid.UUID, *, for_update: bool = False) -> LedgerAccount | None:
    stmt = select(LedgerAccount).where(LedgerAccount.id == account_id)
    if for_update:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


async def transaction_exists(db: AsyncSession, idempotency_key: str) -> bool:
    stmt = select(LedgerTransaction.id).where(LedgerTransaction.idempotency_key == idempotency_key)
    return (await db.execute(stmt)).first() is not None


def add_transaction(db: AsyncSession, transaction: LedgerTransaction) -> None:
    db.add(transaction)


@dataclass
class RawBalance:
    """Sommes brutes des écritures d'un compte (débit > 0, crédit < 0)."""

    total: int = 0
    # Somme des écritures déjà disponibles : tous les débits (un retrait
    # réserve l'argent tout de suite) + les crédits dont available_at est passé.
    available: int = 0


async def raw_balances(db: AsyncSession, account_ids: list[uuid.UUID], now: datetime) -> dict[uuid.UUID, RawBalance]:
    if not account_ids:
        return {}
    available_expr = func.coalesce(
        func.sum(case(((LedgerEntry.amount > 0) | (LedgerEntry.available_at <= now), LedgerEntry.amount), else_=0)),
        0,
    )
    stmt = (
        select(LedgerEntry.account_id, func.coalesce(func.sum(LedgerEntry.amount), 0), available_expr)
        .where(LedgerEntry.account_id.in_(account_ids))
        .group_by(LedgerEntry.account_id)
    )
    result = {account_id: RawBalance() for account_id in account_ids}
    for account_id, total, available in (await db.execute(stmt)).all():
        result[account_id] = RawBalance(total=int(total), available=int(available))
    return result


async def list_accounts(db: AsyncSession, kinds: tuple[AccountKind, ...]) -> list[LedgerAccount]:
    stmt = select(LedgerAccount).where(LedgerAccount.kind.in_(kinds)).order_by(LedgerAccount.created_at)
    return list((await db.execute(stmt)).scalars().all())


async def list_entries_for_account(
    db: AsyncSession, account_id: uuid.UUID, params: PageParams
) -> tuple[list[tuple[LedgerEntry, LedgerTransaction]], int]:
    base = (
        select(LedgerEntry, LedgerTransaction)
        .join(LedgerTransaction, LedgerEntry.transaction_id == LedgerTransaction.id)
        .where(LedgerEntry.account_id == account_id)
    )
    total = (
        await db.execute(select(func.count()).select_from(LedgerEntry).where(LedgerEntry.account_id == account_id))
    ).scalar_one()
    stmt = base.order_by(LedgerTransaction.created_at.desc()).offset(params.offset).limit(params.page_size)
    return [(entry, tx) for entry, tx in (await db.execute(stmt)).all()], total


async def list_transactions(db: AsyncSession, params: PageParams) -> tuple[list[LedgerTransaction], int]:
    total = (await db.execute(select(func.count()).select_from(LedgerTransaction))).scalar_one()
    stmt = (
        select(LedgerTransaction)
        .options(selectinload(LedgerTransaction.entries))
        .order_by(LedgerTransaction.created_at.desc())
        .offset(params.offset)
        .limit(params.page_size)
    )
    return list((await db.execute(stmt)).scalars().all()), total


async def sum_by_transaction_kind(db: AsyncSession, account_id: uuid.UUID) -> dict[str, int]:
    """Cumul des mouvements d'un compte par type d'opération (tableau de bord admin)."""
    stmt = (
        select(LedgerTransaction.kind, func.coalesce(func.sum(LedgerEntry.amount), 0))
        .join(LedgerTransaction, LedgerEntry.transaction_id == LedgerTransaction.id)
        .where(LedgerEntry.account_id == account_id)
        .group_by(LedgerTransaction.kind)
    )
    return {kind.value: int(total) for kind, total in (await db.execute(stmt)).all()}


# --- Retraits -------------------------------------------------------------------


def add_withdrawal(db: AsyncSession, withdrawal: Withdrawal) -> None:
    db.add(withdrawal)


async def get_withdrawal(db: AsyncSession, withdrawal_id: uuid.UUID, *, for_update: bool = False) -> Withdrawal | None:
    stmt = select(Withdrawal).where(Withdrawal.id == withdrawal_id)
    if for_update:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_withdrawal_by_payout_id(db: AsyncSession, payout_id: str) -> Withdrawal | None:
    stmt = select(Withdrawal).where(Withdrawal.djomy_payout_id == payout_id).with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_withdrawals_for_account(db: AsyncSession, account_id: uuid.UUID) -> list[Withdrawal]:
    stmt = select(Withdrawal).where(Withdrawal.account_id == account_id).order_by(Withdrawal.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def list_withdrawals(db: AsyncSession, status: WithdrawalStatus | None) -> list[Withdrawal]:
    stmt = select(Withdrawal).order_by(Withdrawal.created_at.desc())
    if status is not None:
        stmt = stmt.where(Withdrawal.status == status)
    return list((await db.execute(stmt.limit(200))).scalars().all())


async def withdrawal_stats(db: AsyncSession) -> dict[WithdrawalStatus, tuple[int, int]]:
    stmt = select(Withdrawal.status, func.count(), func.coalesce(func.sum(Withdrawal.amount), 0)).group_by(
        Withdrawal.status
    )
    return {status: (int(count), int(total)) for status, count, total in (await db.execute(stmt)).all()}


# --- NdjouriBank (acheteurs) ------------------------------------------------------


def add_topup(db: AsyncSession, topup: WalletTopUp) -> None:
    db.add(topup)


async def get_topup(db: AsyncSession, topup_id: uuid.UUID, *, for_update: bool = False) -> WalletTopUp | None:
    stmt = select(WalletTopUp).where(WalletTopUp.id == topup_id)
    if for_update:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_topups_for_user(db: AsyncSession, user_id: uuid.UUID, limit: int = 20) -> list[WalletTopUp]:
    stmt = (
        select(WalletTopUp)
        .where(WalletTopUp.user_id == user_id)
        .order_by(WalletTopUp.created_at.desc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


async def refunded_to_wallet(db: AsyncSession, order_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Montant remboursé sur le solde NdjouriBank, par commande."""
    if not order_ids:
        return {}
    stmt = (
        select(LedgerTransaction.order_id, func.coalesce(func.sum(LedgerEntry.amount), 0))
        .join(LedgerEntry, LedgerEntry.transaction_id == LedgerTransaction.id)
        .where(
            LedgerTransaction.kind == TransactionKind.REFUND_TO_WALLET,
            LedgerTransaction.order_id.in_(order_ids),
            LedgerEntry.amount > 0,
        )
        .group_by(LedgerTransaction.order_id)
    )
    return {order_id: int(total) for order_id, total in (await db.execute(stmt)).all()}
