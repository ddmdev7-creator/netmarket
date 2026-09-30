"""Écritures du grand livre et retraits.

Points d'entrée appelés par les autres modules :
- record_payment_captured : paiement en ligne confirmé (webhook/sync Djomy,
  app/payments/service.py) → l'argent entre en trésorerie, au séquestre.
- settle_sub_order : sous-commande livrée (app/orders/service.py::
  update_sub_order_status) → le séquestre est réparti entre vendeur,
  livreur, point de retrait et Ndjouri.
- record_refund_completed : remboursement Djomy confirmé → sort du séquestre.

Tout est idempotent (LedgerTransaction.idempotency_key) : un webhook rejoué
ou une livraison confirmée deux fois n'écrivent jamais deux fois. Aucune
fonction ne commit, sauf celles appelées directement par un routeur
(retraits, moyen de réception) — les autres s'inscrivent dans la
transaction de l'appelant.

Les commandes payées à la livraison (espèces) restent hors du grand livre
pour l'instant (phase 4 du chantier). Le solde NdjouriBank des acheteurs
(recharges, paiement avec le solde, remboursements) est dans
buyer_service.py et s'appuie sur les mêmes écritures.
"""

import logging
import math
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.pagination import PageParams
from app.couriers import repository as couriers_repository
from app.common.parcel import ParcelSize, pickup_fee_for
from app.orders.models import DeliveryType, Order, OrderStatus, PaymentMethod, SubOrder, SubOrderStatusEvent
from app.payments import djomy_client
from app.payments import repository as payments_repository
from app.payments.models import PaymentStatus
from app.pickup_point_managers import repository as managers_repository
from app.pickup_points import repository as pickup_points_repository
from app.users import repository as users_repository
from app.users.models import User
from app.vendors import repository as vendors_repository
from app.wallets import repository
from app.wallets.models import (
    BENEFICIARY_KINDS,
    AccountKind,
    LedgerAccount,
    LedgerEntry,
    LedgerTransaction,
    TransactionKind,
    Withdrawal,
    WithdrawalStatus,
)
from app.wallets.repository import RawBalance
from app.wallets.schemas import (
    AdminFinanceOverview,
    AdminWalletRead,
    AdminWithdrawalRead,
    EarningsSettingsUpdate,
    LedgerEntryLine,
    LedgerTransactionRead,
    PayoutMethodUpdate,
    WalletBalance,
    WalletEntryRead,
    WalletRead,
)

logger = logging.getLogger(__name__)

SYSTEM_LABELS = {
    AccountKind.DJOMY_TREASURY: "Trésorerie Djomy",
    AccountKind.ORDER_ESCROW: "Séquestre commandes",
    AccountKind.PLATFORM_REVENUE: "Revenus Ndjouri",
    AccountKind.WITHDRAWALS_PENDING: "Retraits en cours",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _short(order_id: uuid.UUID) -> str:
    return f"#GN-{str(order_id)[:5].upper()}"


Line = tuple[LedgerAccount, int, datetime | None]

# Moyens de paiement dont l'argent passe par le séquestre du grand livre.
SEQUESTERED_METHODS = (PaymentMethod.ONLINE, PaymentMethod.WALLET)


async def _post(
    db: AsyncSession,
    *,
    kind: TransactionKind,
    key: str,
    description: str,
    lines: list[Line],
    order_id: uuid.UUID | None = None,
    sub_order_id: uuid.UUID | None = None,
    withdrawal_id: uuid.UUID | None = None,
) -> bool:
    """Écrit une transaction équilibrée. Retourne False (sans rien écrire) si
    la clé a déjà été utilisée."""
    lines = [line for line in lines if line[1] != 0]
    if sum(amount for _, amount, _ in lines) != 0:
        raise ValueError(f"Transaction déséquilibrée ({key}) : {[(a.kind, m) for a, m, _ in lines]}")
    if await repository.transaction_exists(db, key):
        return False
    now = _now()
    transaction = LedgerTransaction(
        kind=kind,
        idempotency_key=key,
        description=description[:300],
        order_id=order_id,
        sub_order_id=sub_order_id,
        withdrawal_id=withdrawal_id,
        created_at=now,
        entries=[
            LedgerEntry(account_id=account.id, amount=amount, available_at=available_at or now)
            for account, amount, available_at in lines
        ],
    )
    repository.add_transaction(db, transaction)
    await db.flush()
    return True


async def _system(db: AsyncSession, kind: AccountKind) -> LedgerAccount:
    return await repository.get_or_create_account(db, kind)


# --- Encaissements et répartition ------------------------------------------------


async def record_payment_captured(db: AsyncSession, order: Order) -> None:
    """Paiement en ligne confirmé : l'argent est chez Djomy, en séquestre
    tant que la commande n'est pas livrée. Répartit aussitôt les
    sous-commandes déjà livrées (webhook arrivé après la livraison)."""
    if order.payment_method != PaymentMethod.ONLINE:
        return
    await _post_capture(db, order)
    for sub_order in order.sub_orders:
        await settle_sub_order(db, order, sub_order)


async def _post_capture(db: AsyncSession, order: Order) -> None:
    treasury = await _system(db, AccountKind.DJOMY_TREASURY)
    escrow = await _system(db, AccountKind.ORDER_ESCROW)
    await _post(
        db,
        kind=TransactionKind.PAYMENT_CAPTURED,
        key=f"capture:{order.id}",
        description=f"Paiement en ligne reçu — commande {_short(order.id)}",
        lines=[(treasury, order.total, None), (escrow, -order.total, None)],
        order_id=order.id,
    )


async def committed_pickup_offers(db: AsyncSession, vendor_id: uuid.UUID) -> int:
    """Frais de « Retrait offert » que le vendeur s'est engagé à payer sur des
    colis pas encore livrés ni annulés — prélevés à la livraison, donc tenus
    en réserve sur son solde disponible (voir app/orders/pickup_offer.py)."""
    total = (
        await db.execute(
            select(func.coalesce(func.sum(SubOrder.vendor_delivery_fee), 0)).where(
                SubOrder.vendor_id == vendor_id,
                SubOrder.vendor_delivery_fee > 0,
                SubOrder.status.notin_([OrderStatus.DELIVERED, OrderStatus.CANCELLED]),
            )
        )
    ).scalar_one()
    return int(total)


async def pickup_point_fee(db: AsyncSession, settings_row, sub_order: SubOrder, pickup_point_id: uuid.UUID) -> tuple[int, str]:
    """Rémunération du point pour un colis remis (décision 2026-09-30) :
    tarif selon la taille du colis, + garde prolongée (par jour au-delà des
    jours gratuits, plafonnée), + bonus volume au-delà de N colis remis dans
    le mois. Renvoie (montant, détail lisible pour le journal)."""
    size = sub_order.parcel_size or ParcelSize.S
    base = pickup_fee_for(settings_row, size)
    parts = [f"taille {size} {base}"]

    arrived_at = (
        await db.execute(
            select(func.min(SubOrderStatusEvent.created_at)).where(
                SubOrderStatusEvent.sub_order_id == sub_order.id,
                SubOrderStatusEvent.status == OrderStatus.ARRIVED_AT_PICKUP_POINT,
            )
        )
    ).scalar_one_or_none()
    storage = 0
    if arrived_at is not None:
        days = int((_now() - arrived_at) / timedelta(days=1))
        billable = max(0, min(days, settings_row.pickup_storage_max_days) - settings_row.pickup_storage_free_days)
        storage = billable * settings_row.pickup_storage_fee_per_day
        if storage:
            parts.append(f"garde {billable} j {storage}")

    month_start = _now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    delivered_this_month = (
        await db.execute(
            select(func.count())
            .select_from(SubOrder)
            .join(Order, Order.id == SubOrder.order_id)
            .where(
                Order.pickup_point_id == pickup_point_id,
                SubOrder.status == OrderStatus.DELIVERED,
                SubOrder.id != sub_order.id,
                SubOrder.updated_at >= month_start,
            )
        )
    ).scalar_one()
    bonus = 0
    if delivered_this_month >= settings_row.pickup_volume_bonus_threshold:
        bonus = round((base + storage) * settings_row.pickup_volume_bonus_percent / 100)
        parts.append(f"bonus volume {bonus}")
    return base + storage + bonus, ", ".join(parts)


async def settle_sub_order(db: AsyncSession, order: Order, sub_order: SubOrder) -> None:
    """Sous-commande livrée et payée en ligne ou avec le solde NdjouriBank :
    le séquestre (montant + frais de livraison) est réparti. Les gains des
    bénéficiaires ne sont retirables qu'après le délai de sécurité réglé par
    l'admin."""
    if order.payment_method not in SEQUESTERED_METHODS or sub_order.status != OrderStatus.DELIVERED:
        return
    if await repository.transaction_exists(db, f"settle:{sub_order.id}"):
        return
    payment = await payments_repository.get_by_order_id(db, order.id)
    if payment is None or payment.status != PaymentStatus.PAID:
        # Paiement pas (encore) confirmé : la répartition se fera à la
        # capture (record_payment_captured).
        return
    if order.payment_method == PaymentMethod.ONLINE:
        # Paiement confirmé avant la mise en place du grand livre : on rattrape
        # la capture. (Payé avec le solde : le séquestre a été alimenté au
        # checkout, voir buyer_service.pay_order.)
        await _post_capture(db, order)

    settings_row = await payments_repository.get_settings(db)
    escrow = await _system(db, AccountKind.ORDER_ESCROW)
    revenue = await _system(db, AccountKind.PLATFORM_REVENUE)
    vendor_account = await repository.get_or_create_account(db, AccountKind.VENDOR, sub_order.vendor_id)
    hold_until = _now() + timedelta(days=settings_row.earnings_hold_days)

    gross = sub_order.amount + sub_order.delivery_fee
    vendor_net = sub_order.amount - sub_order.commission
    # « Retrait offert » : la course payée par le vendeur est prélevée tout de
    # suite (disponible immédiatement), ses gains de la vente restent soumis
    # au délai habituel.
    offered = sub_order.vendor_delivery_fee or 0
    fee = sub_order.delivery_fee + offered
    courier_share = 0
    lines: list[Line] = [
        (escrow, gross, None),
        (vendor_account, -vendor_net, hold_until),
        (vendor_account, offered, None),
    ]
    details = [f"vendeur {vendor_net}"]
    if offered:
        details.append(f"retrait offert par le vendeur {offered}")

    if sub_order.courier_id is not None and fee > 0:
        courier_share = round(fee * settings_row.courier_delivery_share_percent / 100)
        courier_account = await repository.get_or_create_account(db, AccountKind.COURIER, sub_order.courier_id)
        lines.append((courier_account, -courier_share, hold_until))
        details.append(f"livreur {courier_share} ({settings_row.courier_delivery_share_percent} %)")

    pickup_fee = 0
    if order.delivery_type == DeliveryType.PICKUP_POINT and order.pickup_point_id is not None:
        pickup_fee, pickup_detail = await pickup_point_fee(db, settings_row, sub_order, order.pickup_point_id)
        point_account = await repository.get_or_create_account(db, AccountKind.PICKUP_POINT, order.pickup_point_id)
        lines.append((point_account, -pickup_fee, hold_until))
        details.append(f"point de retrait {pickup_fee} ({pickup_detail})")

    platform = sub_order.commission + fee - courier_share - pickup_fee
    lines.append((revenue, -platform, None))
    details.append(f"Ndjouri {platform}")

    await _post(
        db,
        kind=TransactionKind.SUB_ORDER_SETTLED,
        key=f"settle:{sub_order.id}",
        description=f"Livraison {_short(order.id)} · {sub_order.shop_name} — " + ", ".join(details),
        lines=lines,
        order_id=order.id,
        sub_order_id=sub_order.id,
    )


async def record_refund_completed(db: AsyncSession, order: Order) -> None:
    """Remboursement Djomy confirmé : l'argent quitte la trésorerie."""
    if order.payment_method != PaymentMethod.ONLINE:
        return
    await _post_capture(db, order)
    treasury = await _system(db, AccountKind.DJOMY_TREASURY)
    escrow = await _system(db, AccountKind.ORDER_ESCROW)
    await _post(
        db,
        kind=TransactionKind.REFUND_COMPLETED,
        key=f"refund:{order.id}",
        description=f"Remboursement acheteur — commande {_short(order.id)}",
        lines=[(escrow, order.total, None), (treasury, -order.total, None)],
        order_id=order.id,
    )


# --- Soldes ---------------------------------------------------------------------


def _holder_balance(kind: AccountKind, raw: RawBalance) -> WalletBalance:
    sign = 1 if kind == AccountKind.DJOMY_TREASURY else -1
    total, available = sign * raw.total, sign * raw.available
    return WalletBalance(available=available, pending=total - available, total=total)


async def _balances(db: AsyncSession, accounts: list[LedgerAccount]) -> dict[uuid.UUID, WalletBalance]:
    raws = await repository.raw_balances(db, [a.id for a in accounts], _now())
    return {a.id: _holder_balance(a.kind, raws[a.id]) for a in accounts}


async def _in_progress_by_account(db: AsyncSession, account_ids: set[uuid.UUID]) -> dict[uuid.UUID, int]:
    result: dict[uuid.UUID, int] = {}
    for status in (WithdrawalStatus.PENDING, WithdrawalStatus.PROCESSING):
        for withdrawal in await repository.list_withdrawals(db, status):
            if withdrawal.account_id in account_ids:
                result[withdrawal.account_id] = result.get(withdrawal.account_id, 0) + withdrawal.amount
    return result


async def _owner_label(db: AsyncSession, account: LedgerAccount) -> str:
    if account.kind in SYSTEM_LABELS:
        return SYSTEM_LABELS[account.kind]
    if account.kind == AccountKind.VENDOR:
        vendor = await vendors_repository.get_by_id(db, account.owner_id)
        return vendor.shop_name if vendor else "Boutique supprimée"
    if account.kind == AccountKind.COURIER:
        courier = await couriers_repository.get_by_id(db, account.owner_id)
        return (courier.full_name or courier.phone) if courier else "Livreur supprimé"
    if account.kind == AccountKind.BUYER:
        buyer = await users_repository.get_by_id(db, account.owner_id)
        if buyer is None:
            return "Acheteur supprimé"
        return " ".join(filter(None, [buyer.first_name, buyer.last_name])).strip() or buyer.phone
    point = await pickup_points_repository.get_by_id(db, account.owner_id)
    return point.name if point else "Point de retrait supprimé"


# --- Portefeuilles des bénéficiaires ---------------------------------------------


async def _owned_account_keys(db: AsyncSession, user: User) -> list[tuple[AccountKind, uuid.UUID]]:
    keys: list[tuple[AccountKind, uuid.UUID]] = []
    vendor = await vendors_repository.get_by_user_id(db, user.id)
    if vendor is not None:
        keys.append((AccountKind.VENDOR, vendor.id))
    courier = await couriers_repository.get_by_user_id(db, user.id)
    if courier is not None:
        keys.append((AccountKind.COURIER, courier.id))
    manager = await managers_repository.get_by_user_id(db, user.id)
    if manager is not None and manager.pickup_point_id is not None:
        keys.append((AccountKind.PICKUP_POINT, manager.pickup_point_id))
    return keys


async def _require_owned_account(
    db: AsyncSession, user: User, account_id: uuid.UUID, *, for_update: bool = False
) -> LedgerAccount:
    account = await repository.get_account(db, account_id, for_update=for_update)
    if account is None or account.kind not in BENEFICIARY_KINDS:
        raise NotFoundError("Portefeuille introuvable.")
    if (account.kind, account.owner_id) not in await _owned_account_keys(db, user):
        raise ForbiddenError("Ce portefeuille ne vous appartient pas.")
    return account


async def _wallet_read(db: AsyncSession, account: LedgerAccount) -> WalletRead:
    settings_row = await payments_repository.get_settings(db)
    balance = (await _balances(db, [account]))[account.id]
    in_progress = (await _in_progress_by_account(db, {account.id})).get(account.id, 0)
    return WalletRead(
        id=account.id,
        kind=account.kind,
        owner_id=account.owner_id,
        owner_label=await _owner_label(db, account),
        balance=balance,
        withdrawals_in_progress=in_progress,
        committed_offers=(
            await committed_pickup_offers(db, account.owner_id)
            if account.kind == AccountKind.VENDOR and account.owner_id
            else 0
        ),
        payout_provider=account.payout_provider,
        payout_account_number=account.payout_account_number,
        payout_beneficiary_name=account.payout_beneficiary_name,
        min_withdrawal_amount=settings_row.min_withdrawal_amount,
        withdrawal_fee_percent=float(settings_row.withdrawal_fee_percent),
        earnings_hold_days=settings_row.earnings_hold_days,
    )


async def list_my_wallets(db: AsyncSession, user: User) -> list[WalletRead]:
    wallets = []
    for kind, owner_id in await _owned_account_keys(db, user):
        account = await repository.get_or_create_account(db, kind, owner_id)
        wallets.append(await _wallet_read(db, account))
    await db.commit()
    return wallets


async def list_my_entries(
    db: AsyncSession, user: User, account_id: uuid.UUID, params: PageParams
) -> tuple[list[WalletEntryRead], int]:
    account = await _require_owned_account(db, user, account_id)
    rows, total = await repository.list_entries_for_account(db, account.id, params)
    now = _now()
    return [
        WalletEntryRead(
            id=entry.id,
            created_at=tx.created_at,
            kind=tx.kind,
            description=tx.description,
            amount=-entry.amount,
            available_at=entry.available_at,
            is_pending=entry.amount < 0 and entry.available_at > now,
            order_id=tx.order_id,
            sub_order_id=tx.sub_order_id,
            withdrawal_id=tx.withdrawal_id,
        )
        for entry, tx in rows
    ], total


async def update_payout_method(
    db: AsyncSession, user: User, account_id: uuid.UUID, data: PayoutMethodUpdate
) -> WalletRead:
    account = await _require_owned_account(db, user, account_id, for_update=True)
    account.payout_provider = data.payout_provider
    account.payout_account_number = data.payout_account_number
    account.payout_beneficiary_name = data.payout_beneficiary_name.strip()
    await db.commit()
    return await _wallet_read(db, account)


# --- Retraits -------------------------------------------------------------------


async def request_withdrawal(db: AsyncSession, user: User, account_id: uuid.UUID, amount: int) -> Withdrawal:
    # Verrou sur le compte : deux demandes simultanées ne peuvent pas
    # dépenser deux fois le même solde disponible.
    account = await _require_owned_account(db, user, account_id, for_update=True)
    if not account.payout_provider or not account.payout_account_number or not account.payout_beneficiary_name:
        raise ConflictError("Renseignez d'abord votre moyen de réception (Orange Money, MoMo…).")

    settings_row = await payments_repository.get_settings(db)
    if amount < settings_row.min_withdrawal_amount:
        raise ConflictError(f"Le montant minimum d'un retrait est de {settings_row.min_withdrawal_amount} GNF.")
    balance = (await _balances(db, [account]))[account.id]
    if amount > balance.available:
        raise ConflictError(f"Solde disponible insuffisant ({balance.available} GNF).")
    if account.kind == AccountKind.VENDOR and account.owner_id is not None:
        committed = await committed_pickup_offers(db, account.owner_id)
        if amount > balance.available - committed:
            raise ConflictError(
                f"{committed} GNF sont réservés pour les retraits offerts de commandes en cours : "
                f"vous pouvez retirer au plus {max(0, balance.available - committed)} GNF."
            )

    fee_percent = float(settings_row.withdrawal_fee_percent)
    fee = math.ceil(amount * fee_percent / 100)
    if amount - fee < 1:
        raise ConflictError("Montant trop faible une fois les frais déduits.")

    withdrawal = Withdrawal(
        account_id=account.id,
        requested_by=user.id,
        amount=amount,
        fee=fee,
        net_amount=amount - fee,
        fee_percent=fee_percent,
        payout_provider=account.payout_provider,
        payout_account_number=account.payout_account_number,
        payout_beneficiary_name=account.payout_beneficiary_name,
    )
    repository.add_withdrawal(db, withdrawal)
    await db.flush()

    reserved = await _system(db, AccountKind.WITHDRAWALS_PENDING)
    await _post(
        db,
        kind=TransactionKind.WITHDRAWAL_REQUESTED,
        key=f"withdrawal:{withdrawal.id}:request",
        description=f"Demande de retrait vers {account.payout_provider.value} {account.payout_account_number}",
        lines=[(account, amount, None), (reserved, -amount, None)],
        withdrawal_id=withdrawal.id,
    )
    await db.commit()
    await db.refresh(withdrawal)
    return withdrawal


async def _reverse_withdrawal(db: AsyncSession, withdrawal: Withdrawal, reason: str) -> None:
    account = await repository.get_account(db, withdrawal.account_id)
    reserved = await _system(db, AccountKind.WITHDRAWALS_PENDING)
    await _post(
        db,
        kind=TransactionKind.WITHDRAWAL_REVERSED,
        key=f"withdrawal:{withdrawal.id}:reverse",
        description=f"Retrait annulé — {reason}",
        lines=[(reserved, withdrawal.amount, None), (account, -withdrawal.amount, None)],
        withdrawal_id=withdrawal.id,
    )


async def list_my_withdrawals(db: AsyncSession, user: User, account_id: uuid.UUID) -> list[Withdrawal]:
    account = await _require_owned_account(db, user, account_id)
    return await repository.list_withdrawals_for_account(db, account.id)


async def cancel_my_withdrawal(db: AsyncSession, user: User, withdrawal_id: uuid.UUID) -> Withdrawal:
    withdrawal = await repository.get_withdrawal(db, withdrawal_id, for_update=True)
    if withdrawal is None:
        raise NotFoundError("Retrait introuvable.")
    await _require_owned_account(db, user, withdrawal.account_id)
    if withdrawal.status != WithdrawalStatus.PENDING:
        raise ConflictError("Ce retrait est déjà en cours de traitement et ne peut plus être annulé.")
    await _reverse_withdrawal(db, withdrawal, "annulé par le bénéficiaire")
    withdrawal.status = WithdrawalStatus.CANCELLED
    withdrawal.processed_at = _now()
    await db.commit()
    await db.refresh(withdrawal)
    return withdrawal


async def _admin_withdrawal_read(db: AsyncSession, withdrawal: Withdrawal) -> AdminWithdrawalRead:
    account = await repository.get_account(db, withdrawal.account_id)
    read = AdminWithdrawalRead.model_validate(
        {
            **{k: getattr(withdrawal, k) for k in AdminWithdrawalRead.model_fields if hasattr(withdrawal, k)},
            "account_kind": account.kind,
            "owner_label": await _owner_label(db, account),
        }
    )
    return read


async def admin_list_withdrawals(db: AsyncSession, status: WithdrawalStatus | None) -> list[AdminWithdrawalRead]:
    return [await _admin_withdrawal_read(db, w) for w in await repository.list_withdrawals(db, status)]


async def _get_for_admin(db: AsyncSession, withdrawal_id: uuid.UUID) -> Withdrawal:
    withdrawal = await repository.get_withdrawal(db, withdrawal_id, for_update=True)
    if withdrawal is None:
        raise NotFoundError("Retrait introuvable.")
    return withdrawal


async def admin_reject_withdrawal(db: AsyncSession, withdrawal_id: uuid.UUID, reason: str) -> AdminWithdrawalRead:
    withdrawal = await _get_for_admin(db, withdrawal_id)
    if withdrawal.status != WithdrawalStatus.PENDING:
        raise ConflictError("Seul un retrait en attente peut être refusé.")
    await _reverse_withdrawal(db, withdrawal, f"refusé par l'admin : {reason}")
    withdrawal.status = WithdrawalStatus.REJECTED
    withdrawal.admin_note = reason
    withdrawal.processed_at = _now()
    await db.commit()
    return await _admin_withdrawal_read(db, withdrawal)


async def admin_approve_withdrawal(db: AsyncSession, withdrawal_id: uuid.UUID) -> AdminWithdrawalRead:
    """Validation admin : lance le versement Djomy. L'argent reste réservé
    (WITHDRAWALS_PENDING) jusqu'à la confirmation du versement."""
    withdrawal = await _get_for_admin(db, withdrawal_id)
    if withdrawal.status != WithdrawalStatus.PENDING:
        raise ConflictError("Ce retrait n'est plus en attente de validation.")
    try:
        result = await djomy_client.create_payout(
            amount=withdrawal.net_amount,
            account_number=withdrawal.payout_account_number,
            provider_code=withdrawal.payout_provider.value,
            beneficiary_name=withdrawal.payout_beneficiary_name,
            reference=f"WD-{withdrawal.id}",
            message=f"Retrait Ndjouri {str(withdrawal.id)[:8].upper()}",
        )
    except djomy_client.DjomyNotConfiguredError as exc:
        raise ConflictError("Djomy n'est pas configuré sur ce serveur : versement impossible.") from exc
    except httpx.HTTPStatusError as exc:
        logger.warning("Versement Djomy refusé pour le retrait %s : %s", withdrawal.id, exc.response.text)
        raise ConflictError(f"Djomy a refusé le versement : {exc.response.text[:200]}") from exc
    except httpx.HTTPError as exc:
        raise ConflictError("Djomy est injoignable, réessayez dans quelques minutes.") from exc

    withdrawal.status = WithdrawalStatus.PROCESSING
    withdrawal.djomy_order_id = result["order_id"]
    withdrawal.djomy_payout_id = result["payout_id"]
    withdrawal.djomy_total_amount = result["total_amount_to_pay"]
    await db.commit()
    return await _admin_withdrawal_read(db, withdrawal)


async def _apply_payout_outcome(
    db: AsyncSession, withdrawal: Withdrawal, djomy_status: str, total_amount: int | None
) -> None:
    if withdrawal.status != WithdrawalStatus.PROCESSING:
        return
    if djomy_status == "SUCCESS":
        # Djomy prélève net + ses frais réels ; le bénéficiaire a payé les
        # frais estimés. L'écart (en plus ou en moins) revient à Ndjouri.
        total = total_amount or withdrawal.djomy_total_amount or withdrawal.net_amount
        account = await repository.get_account(db, withdrawal.account_id)
        treasury = await _system(db, AccountKind.DJOMY_TREASURY)
        reserved = await _system(db, AccountKind.WITHDRAWALS_PENDING)
        revenue = await _system(db, AccountKind.PLATFORM_REVENUE)
        await _post(
            db,
            kind=TransactionKind.WITHDRAWAL_PAID,
            key=f"withdrawal:{withdrawal.id}:paid",
            description=(
                f"Retrait versé à {await _owner_label(db, account)} : {withdrawal.net_amount} GNF "
                f"(frais Djomy {total - withdrawal.net_amount}, frais facturés {withdrawal.fee})"
            ),
            lines=[(reserved, withdrawal.amount, None), (treasury, -total, None), (revenue, total - withdrawal.amount, None)],
            withdrawal_id=withdrawal.id,
        )
        withdrawal.status = WithdrawalStatus.PAID
        withdrawal.djomy_total_amount = total
        withdrawal.processed_at = _now()
    elif djomy_status in ("FAILED", "REJECTED"):
        await _reverse_withdrawal(db, withdrawal, "versement échoué chez Djomy")
        withdrawal.status = WithdrawalStatus.FAILED
        withdrawal.admin_note = "Versement échoué ou rejeté par Djomy — le montant a été recrédité."
        withdrawal.processed_at = _now()


async def admin_sync_withdrawal(db: AsyncSession, withdrawal_id: uuid.UUID) -> AdminWithdrawalRead:
    """Relit le statut du versement chez Djomy (utile tant que le webhook
    n'est pas enregistré dans le tableau de bord Djomy)."""
    withdrawal = await _get_for_admin(db, withdrawal_id)
    if withdrawal.status == WithdrawalStatus.PROCESSING and withdrawal.djomy_order_id and withdrawal.djomy_payout_id:
        try:
            data = await djomy_client.get_payout(withdrawal.djomy_order_id, withdrawal.djomy_payout_id)
        except (djomy_client.DjomyNotConfiguredError, httpx.HTTPError) as exc:
            raise ConflictError("Impossible de joindre Djomy pour vérifier ce versement.") from exc
        total = data.get("totalAmountToPay")
        await _apply_payout_outcome(db, withdrawal, data.get("status", ""), int(total) if total is not None else None)
        await db.commit()
    return await _admin_withdrawal_read(db, withdrawal)


async def apply_withdrawal_payout_event(
    db: AsyncSession, *, payout_id: str, event_type: str, total_amount: int | None
) -> bool:
    """Webhook payout.* d'un retrait. Retourne False si aucun retrait ne correspond."""
    withdrawal = await repository.get_withdrawal_by_payout_id(db, payout_id)
    if withdrawal is None:
        return False
    status = {"payout.success": "SUCCESS", "payout.failed": "FAILED"}.get(event_type)
    if status is not None:
        await _apply_payout_outcome(db, withdrawal, status, total_amount)
        await db.commit()
    return True


# --- Compte principal (admin) ----------------------------------------------------


async def admin_overview(db: AsyncSession) -> AdminFinanceOverview:
    system = {kind: await _system(db, kind) for kind in SYSTEM_LABELS}
    beneficiaries = await repository.list_accounts(db, BENEFICIARY_KINDS)
    buyers = await repository.list_accounts(db, (AccountKind.BUYER,))
    balances = await _balances(db, [*system.values(), *beneficiaries, *buyers])

    def bal(kind: AccountKind) -> int:
        return balances[system[kind].id].total

    ben_available = sum(balances[a.id].available for a in beneficiaries)
    ben_total = sum(balances[a.id].total for a in beneficiaries)
    buyers_total = sum(balances[a.id].total for a in buyers)
    treasury_moves = await repository.sum_by_transaction_kind(db, system[AccountKind.DJOMY_TREASURY].id)
    stats = await repository.withdrawal_stats(db)
    pending = stats.get(WithdrawalStatus.PENDING, (0, 0))
    processing = stats.get(WithdrawalStatus.PROCESSING, (0, 0))
    await db.commit()

    escrow, reserved, revenue, treasury = (
        bal(AccountKind.ORDER_ESCROW),
        bal(AccountKind.WITHDRAWALS_PENDING),
        bal(AccountKind.PLATFORM_REVENUE),
        bal(AccountKind.DJOMY_TREASURY),
    )
    return AdminFinanceOverview(
        treasury=treasury,
        escrow=escrow,
        beneficiaries_available=ben_available,
        beneficiaries_pending=ben_total - ben_available,
        beneficiaries_total=ben_total,
        withdrawals_reserved=reserved,
        platform_revenue=revenue,
        buyer_wallets_total=buyers_total,
        buyer_wallets_count=sum(1 for a in buyers if balances[a.id].total),
        is_balanced=treasury == escrow + ben_total + reserved + revenue + buyers_total,
        total_captured=treasury_moves.get(TransactionKind.PAYMENT_CAPTURED.value, 0),
        total_topped_up=treasury_moves.get(TransactionKind.WALLET_TOPUP.value, 0),
        total_refunded=-treasury_moves.get(TransactionKind.REFUND_COMPLETED.value, 0),
        total_paid_out=-treasury_moves.get(TransactionKind.WITHDRAWAL_PAID.value, 0),
        withdrawals_pending_count=pending[0],
        withdrawals_pending_amount=pending[1],
        withdrawals_processing_count=processing[0],
        withdrawals_processing_amount=processing[1],
    )


async def admin_list_wallets(db: AsyncSession) -> list[AdminWalletRead]:
    accounts = await repository.list_accounts(db, (*BENEFICIARY_KINDS, AccountKind.BUYER))
    balances = await _balances(db, accounts)
    in_progress = await _in_progress_by_account(db, {a.id for a in accounts})
    return [
        AdminWalletRead(
            id=a.id,
            kind=a.kind,
            owner_id=a.owner_id,
            owner_label=await _owner_label(db, a),
            balance=balances[a.id],
            withdrawals_in_progress=in_progress.get(a.id, 0),
            payout_provider=a.payout_provider,
            payout_account_number=a.payout_account_number,
        )
        for a in accounts
    ]


async def admin_list_transactions(db: AsyncSession, params: PageParams) -> tuple[list[LedgerTransactionRead], int]:
    transactions, total = await repository.list_transactions(db, params)
    labels: dict[uuid.UUID, tuple[AccountKind, str]] = {}
    result = []
    for tx in transactions:
        lines = []
        for entry in tx.entries:
            if entry.account_id not in labels:
                account = await repository.get_account(db, entry.account_id)
                labels[entry.account_id] = (account.kind, await _owner_label(db, account))
            kind, label = labels[entry.account_id]
            lines.append(LedgerEntryLine(account_kind=kind, owner_label=label, amount=entry.amount))
        result.append(
            LedgerTransactionRead(
                id=tx.id,
                created_at=tx.created_at,
                kind=tx.kind,
                description=tx.description,
                order_id=tx.order_id,
                sub_order_id=tx.sub_order_id,
                withdrawal_id=tx.withdrawal_id,
                lines=sorted(lines, key=lambda line: -line.amount),
            )
        )
    return result, total


async def get_earnings_settings(db: AsyncSession):
    return await payments_repository.get_settings(db)


async def update_earnings_settings(db: AsyncSession, data: EarningsSettingsUpdate):
    settings_row = await payments_repository.get_settings(db)
    # Champs NdjouriBank optionnels : absents = inchangés.
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(settings_row, field, value)
    await db.commit()
    return settings_row


async def get_wallet_balance(db: AsyncSession, kind: AccountKind, owner_id: uuid.UUID) -> WalletBalance | None:
    """Solde d'un portefeuille bénéficiaire (fiches admin) ; None s'il n'existe pas encore."""
    account = (
        await db.execute(select(LedgerAccount).where(LedgerAccount.kind == kind, LedgerAccount.owner_id == owner_id))
    ).scalar_one_or_none()
    if account is None:
        return None
    return (await _balances(db, [account]))[account.id]
