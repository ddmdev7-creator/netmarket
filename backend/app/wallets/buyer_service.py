"""NdjouriBank : solde des acheteurs.

Le solde est un compte BUYER du grand livre (owner_id = User.id), sans
délai de disponibilité et jamais retirable (circuit fermé : il ne se
dépense que sur Ndjouri). Mouvements :
- recharge via le portail Djomy, créditée à la confirmation (webhook ou
  synchronisation au retour du portail) : trésorerie → solde ;
- commande payée avec le solde (checkout) : solde → séquestre, puis
  répartition à la livraison comme un paiement en ligne
  (service.settle_sub_order) ;
- remboursement sur le solde (commande ou sous-commande annulée) :
  séquestre → solde, immédiat.

payment_settings.buyer_wallet_enabled ferme les recharges et les
remboursements « au choix » sur le solde tant que la conformité n'est pas
validée ; un solde existant reste toujours utilisable, et une commande
payée avec le solde est toujours remboursée dessus.
"""

import logging
import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.pagination import PageParams
from app.orders.models import Order, PaymentMethod
from app.payments import djomy_client
from app.payments import repository as payments_repository
from app.users.models import User
from app.wallets import repository, service
from app.wallets.models import AccountKind, LedgerAccount, TopUpStatus, TransactionKind, WalletTopUp
from app.wallets.schemas import BuyerWalletRead, WalletEntryRead

settings = get_settings()
logger = logging.getLogger(__name__)

# Statuts Djomy (webhook eventType, ou data.status d'un GET) → statut de recharge.
_EVENT_TO_STATUS = {
    "payment.success": TopUpStatus.PAID,
    "payment.failed": TopUpStatus.FAILED,
    "payment.timeout": TopUpStatus.FAILED,
    "payment.cancelled": TopUpStatus.CANCELLED,
}
_DATA_STATUS_TO_STATUS = {
    "SUCCESS": TopUpStatus.PAID,
    "FAILED": TopUpStatus.FAILED,
    "CANCELLED": TopUpStatus.CANCELLED,
}


async def _account(db: AsyncSession, user_id: uuid.UUID, *, for_update: bool = False) -> LedgerAccount:
    return await repository.get_or_create_account(db, AccountKind.BUYER, user_id, for_update=for_update)


async def _balance(db: AsyncSession, account: LedgerAccount) -> int:
    return (await service._balances(db, [account]))[account.id].total


async def get_my_wallet(db: AsyncSession, user: User) -> BuyerWalletRead:
    settings_row = await payments_repository.get_settings(db)
    account = await _account(db, user.id)
    balance = await _balance(db, account)
    await db.commit()
    return BuyerWalletRead(
        enabled=settings_row.buyer_wallet_enabled,
        balance=balance,
        topup_min=settings_row.wallet_topup_min,
        topup_max=settings_row.wallet_topup_max,
        max_balance=settings_row.wallet_max_balance,
    )


async def list_my_entries(db: AsyncSession, user: User, params: PageParams) -> tuple[list[WalletEntryRead], int]:
    account = await _account(db, user.id)
    rows, total = await repository.list_entries_for_account(db, account.id, params)
    await db.commit()
    return [
        WalletEntryRead(
            id=entry.id,
            created_at=tx.created_at,
            kind=tx.kind,
            description=tx.description,
            amount=-entry.amount,
            available_at=entry.available_at,
            is_pending=False,
            order_id=tx.order_id,
            sub_order_id=tx.sub_order_id,
            withdrawal_id=tx.withdrawal_id,
        )
        for entry, tx in rows
    ], total


# --- Recharges ------------------------------------------------------------------


async def create_topup(db: AsyncSession, user: User, amount: int, payer_phone: str | None) -> tuple[WalletTopUp, str]:
    settings_row = await payments_repository.get_settings(db)
    if not settings_row.buyer_wallet_enabled:
        raise ConflictError("La recharge NdjouriBank n'est pas encore disponible.")
    if amount < settings_row.wallet_topup_min:
        raise ConflictError(f"Le montant minimum d'une recharge est de {settings_row.wallet_topup_min} GNF.")
    if amount > settings_row.wallet_topup_max:
        raise ConflictError(f"Le montant maximum d'une recharge est de {settings_row.wallet_topup_max} GNF.")
    balance = await _balance(db, await _account(db, user.id))
    if balance + amount > settings_row.wallet_max_balance:
        room = max(settings_row.wallet_max_balance - balance, 0)
        raise ConflictError(
            f"Votre solde ne peut pas dépasser {settings_row.wallet_max_balance} GNF "
            f"(vous pouvez encore recharger {room} GNF)."
        )

    topup = WalletTopUp(user_id=user.id, amount=amount, payer_phone=payer_phone or user.phone)
    repository.add_topup(db, topup)
    await db.flush()
    try:
        transaction_id, redirect_url = await djomy_client.initiate_gateway_payment(
            amount=amount,
            payer_number=topup.payer_phone,
            reference=str(topup.id),
            description=f"Recharge NdjouriBank {str(topup.id)[:8].upper()}",
            return_url=f"{settings.frontend_url}/ndjouribank?topup={topup.id}",
        )
    except djomy_client.DjomyNotConfiguredError as exc:
        raise ConflictError("Le paiement en ligne n'est pas configuré sur ce serveur.") from exc
    except httpx.HTTPError as exc:
        logger.warning("Recharge NdjouriBank refusée par Djomy : %s", exc)
        raise ConflictError("Djomy n'a pas pu démarrer la recharge, réessayez dans quelques minutes.") from exc
    topup.provider_reference = transaction_id
    await db.commit()
    await db.refresh(topup)
    return topup, redirect_url


async def _apply_topup_status(db: AsyncSession, topup: WalletTopUp, status: TopUpStatus) -> None:
    """Seule une recharge encore en attente change de statut ; une recharge
    confirmée crédite le solde (une seule fois, clé d'idempotence)."""
    if topup.status != TopUpStatus.PENDING or status == TopUpStatus.PENDING:
        return
    topup.status = status
    if status != TopUpStatus.PAID:
        return
    topup.confirmed_at = service._now()
    treasury = await service._system(db, AccountKind.DJOMY_TREASURY)
    account = await _account(db, topup.user_id)
    await service._post(
        db,
        kind=TransactionKind.WALLET_TOPUP,
        key=f"topup:{topup.id}",
        description=f"Recharge NdjouriBank via Djomy ({topup.payer_phone})",
        lines=[(treasury, topup.amount, None), (account, -topup.amount, None)],
    )


async def apply_topup_event(db: AsyncSession, *, topup_id: uuid.UUID, event_type: str) -> bool:
    """Webhook payment.* dont la référence est une recharge. Retourne False
    si la référence n'est pas une recharge (c'est alors une commande)."""
    topup = await repository.get_topup(db, topup_id, for_update=True)
    if topup is None:
        return False
    status = _EVENT_TO_STATUS.get(event_type)
    if status is not None:
        await _apply_topup_status(db, topup, status)
        await db.commit()
    return True


async def sync_topup(db: AsyncSession, user: User, topup_id: uuid.UUID) -> WalletTopUp:
    """Relit le statut chez Djomy au retour du portail (filet de sécurité
    tant que le webhook n'est pas arrivé ou pas configuré)."""
    topup = await repository.get_topup(db, topup_id, for_update=True)
    if topup is None or topup.user_id != user.id:
        raise NotFoundError("Recharge introuvable.")
    if topup.status == TopUpStatus.PENDING and topup.provider_reference:
        try:
            data = await djomy_client.get_payment_status(topup.provider_reference)
        except (djomy_client.DjomyNotConfiguredError, httpx.HTTPError) as exc:
            logger.warning("Synchronisation de la recharge %s impossible : %s", topup.id, exc)
            data = {}
        status = _DATA_STATUS_TO_STATUS.get(data.get("status", ""))
        if status is not None:
            await _apply_topup_status(db, topup, status)
    await db.commit()
    await db.refresh(topup)
    return topup


async def list_my_topups(db: AsyncSession, user: User) -> list[WalletTopUp]:
    return await repository.list_topups_for_user(db, user.id)


# --- Paiement et remboursements -----------------------------------------------


def _insufficient(balance: int, total: int) -> ConflictError:
    return ConflictError(
        f"Solde NdjouriBank insuffisant : {balance} GNF disponibles pour une commande de {total} GNF."
    )


async def ensure_can_pay(db: AsyncSession, user: User, total: int) -> None:
    balance = await _balance(db, await _account(db, user.id))
    if balance < total:
        raise _insufficient(balance, total)


async def pay_order(db: AsyncSession, order: Order) -> None:
    """Checkout payé avec le solde : débit immédiat vers le séquestre. Le
    compte est verrouillé pour que deux commandes simultanées ne dépensent
    pas deux fois le même solde. Ne commit pas (transaction du checkout)."""
    account = await _account(db, order.user_id, for_update=True)
    balance = await _balance(db, account)
    if balance < order.total:
        raise _insufficient(balance, order.total)
    escrow = await service._system(db, AccountKind.ORDER_ESCROW)
    await service._post(
        db,
        kind=TransactionKind.WALLET_PAYMENT,
        key=f"wallet-payment:{order.id}",
        description=f"Paiement de la commande {service._short(order.id)}",
        lines=[(account, order.total, None), (escrow, -order.total, None)],
        order_id=order.id,
    )


async def is_enabled(db: AsyncSession) -> bool:
    return (await payments_repository.get_settings(db)).buyer_wallet_enabled


async def refund_to_wallet(
    db: AsyncSession, order: Order, amount: int, *, reason: str, sub_order_id: uuid.UUID | None = None
) -> None:
    """Crédite immédiatement le solde de l'acheteur depuis le séquestre.
    Ne commit pas."""
    if amount <= 0 or order.payment_method not in service.SEQUESTERED_METHODS:
        return
    if order.payment_method == PaymentMethod.ONLINE:
        # Le paiement Djomy doit être au séquestre avant d'en ressortir.
        await service._post_capture(db, order)
    escrow = await service._system(db, AccountKind.ORDER_ESCROW)
    account = await _account(db, order.user_id)
    await service._post(
        db,
        kind=TransactionKind.REFUND_TO_WALLET,
        key=f"refund-wallet:{sub_order_id or order.id}",
        description=f"Remboursement sur NdjouriBank — commande {service._short(order.id)} ({reason})",
        lines=[(escrow, amount, None), (account, -amount, None)],
        order_id=order.id,
        sub_order_id=sub_order_id,
    )


async def refunded_amounts(db: AsyncSession, order_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    return await repository.refunded_to_wallet(db, order_ids)
