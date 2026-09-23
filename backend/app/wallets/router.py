"""Portefeuilles des bénéficiaires (/wallets) et compte principal admin (/admin/finance)."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_role
from app.core.pagination import Page, PageParams, pagination_params
from app.users.models import User, UserRole
from app.wallets import service
from app.wallets.models import WithdrawalStatus
from app.wallets.schemas import (
    AdminFinanceOverview,
    AdminWalletRead,
    AdminWithdrawalRead,
    EarningsSettingsRead,
    EarningsSettingsUpdate,
    LedgerTransactionRead,
    PayoutMethodUpdate,
    WalletEntryRead,
    WalletRead,
    WithdrawalCreate,
    WithdrawalRead,
    WithdrawalReject,
)

router = APIRouter(prefix="/wallets", tags=["wallets"])
admin_router = APIRouter(
    prefix="/admin/finance", tags=["admin"], dependencies=[Depends(require_role(UserRole.ADMIN))]
)


@router.get("/mine", response_model=list[WalletRead])
async def list_my_wallets(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[WalletRead]:
    """Un portefeuille par rôle rémunéré de l'utilisateur (boutique, livreur,
    point de retrait) — vide pour un simple acheteur."""
    return await service.list_my_wallets(db, current_user)


@router.get("/{account_id}/entries", response_model=Page[WalletEntryRead])
async def list_my_entries(
    account_id: uuid.UUID,
    params: PageParams = Depends(pagination_params),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Page[WalletEntryRead]:
    items, total = await service.list_my_entries(db, current_user, account_id, params)
    return Page.create(items=items, total=total, params=params)


@router.put("/{account_id}/payout-method", response_model=WalletRead)
async def update_payout_method(
    account_id: uuid.UUID,
    payload: PayoutMethodUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WalletRead:
    return await service.update_payout_method(db, current_user, account_id, payload)


@router.get("/{account_id}/withdrawals", response_model=list[WithdrawalRead])
async def list_my_withdrawals(
    account_id: uuid.UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[WithdrawalRead]:
    return await service.list_my_withdrawals(db, current_user, account_id)


@router.post("/{account_id}/withdrawals", response_model=WithdrawalRead, status_code=201)
async def request_withdrawal(
    account_id: uuid.UUID,
    payload: WithdrawalCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WithdrawalRead:
    return await service.request_withdrawal(db, current_user, account_id, payload.amount)


@router.post("/withdrawals/{withdrawal_id}/cancel", response_model=WithdrawalRead)
async def cancel_my_withdrawal(
    withdrawal_id: uuid.UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> WithdrawalRead:
    return await service.cancel_my_withdrawal(db, current_user, withdrawal_id)


# --- Admin ----------------------------------------------------------------------


@admin_router.get("/overview", response_model=AdminFinanceOverview)
async def admin_overview(db: AsyncSession = Depends(get_db)) -> AdminFinanceOverview:
    return await service.admin_overview(db)


@admin_router.get("/wallets", response_model=list[AdminWalletRead])
async def admin_list_wallets(db: AsyncSession = Depends(get_db)) -> list[AdminWalletRead]:
    return await service.admin_list_wallets(db)


@admin_router.get("/transactions", response_model=Page[LedgerTransactionRead])
async def admin_list_transactions(
    params: PageParams = Depends(pagination_params), db: AsyncSession = Depends(get_db)
) -> Page[LedgerTransactionRead]:
    items, total = await service.admin_list_transactions(db, params)
    return Page.create(items=items, total=total, params=params)


@admin_router.get("/withdrawals", response_model=list[AdminWithdrawalRead])
async def admin_list_withdrawals(
    status_filter: WithdrawalStatus | None = Query(default=None, alias="status"), db: AsyncSession = Depends(get_db)
) -> list[AdminWithdrawalRead]:
    return await service.admin_list_withdrawals(db, status_filter)


@admin_router.post("/withdrawals/{withdrawal_id}/approve", response_model=AdminWithdrawalRead)
async def admin_approve_withdrawal(withdrawal_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> AdminWithdrawalRead:
    return await service.admin_approve_withdrawal(db, withdrawal_id)


@admin_router.post("/withdrawals/{withdrawal_id}/reject", response_model=AdminWithdrawalRead)
async def admin_reject_withdrawal(
    withdrawal_id: uuid.UUID, payload: WithdrawalReject, db: AsyncSession = Depends(get_db)
) -> AdminWithdrawalRead:
    return await service.admin_reject_withdrawal(db, withdrawal_id, payload.reason)


@admin_router.post("/withdrawals/{withdrawal_id}/sync", response_model=AdminWithdrawalRead)
async def admin_sync_withdrawal(withdrawal_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> AdminWithdrawalRead:
    return await service.admin_sync_withdrawal(db, withdrawal_id)


@admin_router.get("/settings", response_model=EarningsSettingsRead)
async def admin_get_settings(db: AsyncSession = Depends(get_db)) -> EarningsSettingsRead:
    return await service.get_earnings_settings(db)


@admin_router.put("/settings", response_model=EarningsSettingsRead)
async def admin_update_settings(
    payload: EarningsSettingsUpdate, db: AsyncSession = Depends(get_db)
) -> EarningsSettingsRead:
    return await service.update_earnings_settings(db, payload)
