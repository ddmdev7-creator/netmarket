"""Vendor subscription orchestration: subscribing, admin confirmation, premium check."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.subscriptions import repository
from app.subscriptions.schemas import AdminSubscriptionRead
from app.subscriptions.models import SubscriptionPlan, SubscriptionStatus, VendorSubscription
from app.vendors.models import Vendor


async def list_plans(db: AsyncSession) -> list[SubscriptionPlan]:
    return await repository.list_active_plans(db)


async def subscribe(db: AsyncSession, vendor: Vendor, plan_id: uuid.UUID) -> VendorSubscription:
    plan = await repository.get_plan_by_id(db, plan_id)
    if plan is None or not plan.is_active:
        raise NotFoundError("Ce plan d'abonnement n'existe pas.")

    if await repository.has_pending(db, vendor.id):
        raise ConflictError("Une demande d'abonnement est déjà en attente de confirmation.")

    subscription = await repository.create(db, vendor_id=vendor.id, plan_id=plan.id, status=SubscriptionStatus.PENDING)
    subscription.plan = plan
    await db.commit()
    return subscription


async def get_my_subscription(db: AsyncSession, vendor: Vendor) -> VendorSubscription | None:
    return await repository.get_latest_for_vendor(db, vendor.id)


async def is_premium(db: AsyncSession, vendor_id: uuid.UUID) -> bool:
    return await repository.is_premium(db, vendor_id)


async def list_by_status(db: AsyncSession, status: SubscriptionStatus | None) -> list[VendorSubscription]:
    return await repository.list_by_status(db, status)


async def admin_confirm(db: AsyncSession, subscription_id: uuid.UUID) -> VendorSubscription:
    subscription = await repository.get_by_id(db, subscription_id)
    if subscription is None:
        raise NotFoundError("Abonnement introuvable.")
    if subscription.status != SubscriptionStatus.PENDING:
        raise ConflictError("Cette demande n'est pas en attente de confirmation.")

    now = datetime.now(timezone.utc)
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.started_at = now
    subscription.expires_at = now + timedelta(days=subscription.plan.duration_days)
    await db.commit()
    return subscription


async def admin_cancel(db: AsyncSession, subscription_id: uuid.UUID) -> VendorSubscription:
    subscription = await repository.get_by_id(db, subscription_id)
    if subscription is None:
        raise NotFoundError("Abonnement introuvable.")
    if subscription.status not in (SubscriptionStatus.PENDING, SubscriptionStatus.ACTIVE):
        raise ConflictError("Cet abonnement ne peut plus être annulé.")

    subscription.status = SubscriptionStatus.CANCELLED
    await db.commit()
    return subscription


async def admin_list(db: AsyncSession, status: SubscriptionStatus | None) -> list[AdminSubscriptionRead]:
    """Liste admin enrichie de la boutique et de son propriétaire."""
    from sqlalchemy import select

    from app.users.models import User
    from app.vendors.models import Vendor

    subscriptions = await repository.list_by_status(db, status)
    vendor_ids = {s.vendor_id for s in subscriptions}
    rows = (
        await db.execute(select(Vendor, User).join(User, User.id == Vendor.user_id).where(Vendor.id.in_(vendor_ids)))
    ).all() if vendor_ids else []
    owners = {vendor.id: (vendor, user) for vendor, user in rows}
    result = []
    for sub in subscriptions:
        vendor, user = owners.get(sub.vendor_id, (None, None))
        result.append(
            AdminSubscriptionRead.model_validate(sub).model_copy(
                update={
                    "shop_name": vendor.shop_name if vendor else "Boutique supprimée",
                    "vendor_zone": vendor.zone if vendor else None,
                    "vendor_status": vendor.status.value if vendor else None,
                    "owner_user_id": user.id if user else None,
                    "owner_full_name": " ".join(filter(None, [user.first_name, user.last_name])) or None if user else None,
                    "owner_phone": user.phone if user else None,
                    "owner_email": user.email if user else None,
                }
            )
        )
    return result
