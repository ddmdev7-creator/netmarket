"""Vendor subscriptions: subscribing and renewing, trials, admin actions,
and the overview shown on the subscription pages.

Règles (validées avec le métier, 2026-09-30) :
- un abonnement payé est dû : jamais remboursé. Le vendeur ne peut annuler
  qu'une demande encore en attente de paiement ; seul l'admin peut mettre
  fin à un abonnement actif (sans remboursement) ;
- renouveler pendant un abonnement actif ajoute une période qui démarre à
  la fin de la période en cours (started_at futur) ;
- essai gratuit : une fois par formule et par boutique, offert par l'admin
  ou automatiquement à l'approbation de la boutique (SubscriptionSettings) ;
- à la fin, rien n'est supprimé : après grace_days, les produits au-delà du
  quota Gratuit sont masqués (voir app/subscriptions/jobs.py).
"""

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.subscriptions import quotas, repository
from app.subscriptions.models import SubscriptionPlan, SubscriptionStatus, UsageKind, VendorSubscription
from app.subscriptions.schemas import (
    AdminSubscriptionRead,
    QuotaUsage,
    SubscriptionOverview,
    SubscriptionPlanCreate,
    SubscriptionPlanRead,
    SubscriptionPlanUpdate,
    SubscriptionSettingsRead,
    SubscriptionSettingsUpdate,
    VendorSubscriptionRead,
)
from app.vendors.models import Vendor


def _date(value) -> str:
    return value.strftime("%d/%m/%Y")


async def _notify(db: AsyncSession, vendor_id: uuid.UUID, title: str, body: str, *, reminder: bool = False) -> None:
    from app.notifications import service as notifications_service

    vendor = await db.get(Vendor, vendor_id)
    if vendor is not None:
        await notifications_service.notify_subscription(
            db, user_id=vendor.user_id, title=title, body=body, reminder=reminder
        )


# --- Formules -----------------------------------------------------------------


async def list_plans(db: AsyncSession) -> list[SubscriptionPlan]:
    return await repository.list_active_plans(db)


async def _get_sellable_plan(db: AsyncSession, plan_id: uuid.UUID, *, for_admin: bool = False) -> SubscriptionPlan:
    plan = await repository.get_plan_by_id(db, plan_id)
    if plan is None or plan.is_free or (not for_admin and not plan.is_active):
        raise NotFoundError("Cette formule d'abonnement n'existe pas.")
    return plan


async def admin_list_plans(db: AsyncSession) -> list[SubscriptionPlan]:
    return await repository.list_all_plans(db)


async def admin_create_plan(db: AsyncSession, data: SubscriptionPlanCreate) -> SubscriptionPlan:
    plan = SubscriptionPlan(**data.model_dump())
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


async def admin_update_plan(db: AsyncSession, plan_id: uuid.UUID, data: SubscriptionPlanUpdate) -> SubscriptionPlan:
    plan = await repository.get_plan_by_id(db, plan_id)
    if plan is None:
        raise NotFoundError("Formule introuvable.")
    fields = data.model_dump(exclude_unset=True)
    # Champs obligatoires : None n'a de sens que pour les quotas « illimité ».
    for required in ("name", "price_gnf", "duration_days", "is_active", "sort_order", "max_images_per_product",
                     "featured_per_month", "commission_discount"):
        if required in fields and fields[required] is None:
            fields.pop(required)
    if plan.is_free:
        # La formule Gratuit n'est jamais vendue : prix, durée et mise en vente figés.
        for locked in ("price_gnf", "duration_days", "is_active"):
            fields.pop(locked, None)
    for name, value in fields.items():
        setattr(plan, name, value)
    await db.commit()
    await db.refresh(plan)
    return plan


# --- Vendeur ------------------------------------------------------------------


async def subscribe(db: AsyncSession, vendor: Vendor, plan_id: uuid.UUID) -> VendorSubscription:
    plan = await _get_sellable_plan(db, plan_id)
    if await repository.get_pending(db, vendor.id) is not None:
        raise ConflictError("Une demande d'abonnement est déjà en attente de confirmation.")

    subscription = await repository.create(db, vendor_id=vendor.id, plan_id=plan.id, status=SubscriptionStatus.PENDING)
    subscription.plan = plan
    await db.commit()
    return subscription


async def vendor_cancel_pending(db: AsyncSession, vendor: Vendor, subscription_id: uuid.UUID) -> VendorSubscription:
    subscription = await repository.get_by_id(db, subscription_id)
    if subscription is None or subscription.vendor_id != vendor.id:
        raise NotFoundError("Abonnement introuvable.")
    if subscription.status != SubscriptionStatus.PENDING:
        raise ForbiddenError(
            "Un abonnement payé ne peut pas être annulé : il reste actif jusqu'à sa date de fin, sans remboursement."
        )
    subscription.status = SubscriptionStatus.CANCELLED
    subscription.cancelled_at = quotas.now_utc()
    subscription.cancel_reason = "Demande retirée par le vendeur"
    await db.commit()
    return subscription


async def get_my_subscription(db: AsyncSession, vendor: Vendor) -> VendorSubscription | None:
    """En cours si possible, sinon la plus récente (historique)."""
    return await quotas.current_subscription(db, vendor.id) or await repository.get_latest_for_vendor(db, vendor.id)


async def overview(db: AsyncSession, vendor: Vendor) -> SubscriptionOverview:
    now = quotas.now_utc()
    rights = await quotas.entitlements(db, vendor.id)
    plan = rights.plan
    history = await repository.list_for_vendor(db, vendor.id)
    settings_row = await quotas.get_settings(db)

    grace_until = None
    if rights.subscription is None:
        last_end = max(
            (s.expires_at for s in history if s.status in (SubscriptionStatus.EXPIRED, SubscriptionStatus.CANCELLED)
             and s.started_at is not None and s.expires_at is not None and s.expires_at <= now),
            default=None,
        )
        if last_end is not None and last_end + timedelta(days=settings_row.grace_days) > now:
            grace_until = last_end + timedelta(days=settings_row.grace_days)

    free = await quotas.get_free_plan(db)
    plans = [free] + await repository.list_active_plans(db)
    base_rate = float(vendor.commission_rate)
    scheduled = await repository.get_scheduled(db, vendor.id, now)
    pending = await repository.get_pending(db, vendor.id)
    return SubscriptionOverview(
        plan=SubscriptionPlanRead.model_validate(plan),
        current=VendorSubscriptionRead.model_validate(rights.subscription) if rights.subscription else None,
        scheduled=VendorSubscriptionRead.model_validate(scheduled) if scheduled else None,
        pending=VendorSubscriptionRead.model_validate(pending) if pending else None,
        grace_until=grace_until,
        products=QuotaUsage(used=await quotas.count_active_products(db, vendor.id), limit=plan.max_products),
        ai_enhancements=QuotaUsage(
            used=await quotas.usage_this_month(db, vendor.id, UsageKind.AI_ENHANCEMENT),
            limit=plan.ai_enhancements_per_month,
        ),
        ai_resets_at=quotas.next_month_start(now),
        max_images_per_product=plan.max_images_per_product,
        featured_per_month=plan.featured_per_month,
        base_commission_rate=base_rate,
        effective_commission_rate=float(await quotas.effective_commission_rate(db, vendor)),
        history=[VendorSubscriptionRead.model_validate(s) for s in history],
        trial_used_plan_ids=await repository.trial_plan_ids(db, vendor.id),
        plans=[SubscriptionPlanRead.model_validate(p) for p in plans],
    )


# --- Admin --------------------------------------------------------------------


async def _get(db: AsyncSession, subscription_id: uuid.UUID) -> VendorSubscription:
    subscription = await repository.get_by_id(db, subscription_id)
    if subscription is None:
        raise NotFoundError("Abonnement introuvable.")
    return subscription


async def admin_confirm(db: AsyncSession, subscription_id: uuid.UUID) -> VendorSubscription:
    subscription = await _get(db, subscription_id)
    if subscription.status != SubscriptionStatus.PENDING:
        raise ConflictError("Cette demande n'est pas en attente de confirmation.")

    now = quotas.now_utc()
    # Renouvellement : la nouvelle période s'enchaîne sur celle en cours. Un
    # essai en cours s'arrête en revanche dès que le vendeur paie.
    current = await quotas.current_subscription(db, subscription.vendor_id, now)
    if current is not None and current.is_trial:
        current.status = SubscriptionStatus.EXPIRED
        current.expires_at = now
        current.grace_processed_at = now
    start = await repository.latest_active_end(db, subscription.vendor_id, now) or now
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.started_at = start
    subscription.expires_at = start + timedelta(days=subscription.plan.duration_days)
    await db.commit()
    when = "dès maintenant" if start <= now else f"à partir du {_date(start)}"
    await _notify(
        db,
        subscription.vendor_id,
        f"Abonnement {subscription.plan.name} activé",
        f"Votre paiement est confirmé : la formule {subscription.plan.name} s'applique {when}, "
        f"jusqu'au {_date(subscription.expires_at)}.",
    )
    return subscription


async def admin_cancel(db: AsyncSession, subscription_id: uuid.UUID, reason: str | None = None) -> VendorSubscription:
    subscription = await _get(db, subscription_id)
    if subscription.status not in (SubscriptionStatus.PENDING, SubscriptionStatus.ACTIVE):
        raise ConflictError("Cet abonnement ne peut plus être annulé.")

    was_active = subscription.status == SubscriptionStatus.ACTIVE
    now = quotas.now_utc()
    subscription.status = SubscriptionStatus.CANCELLED
    subscription.cancelled_at = now
    # La période de grâce part de l'arrêt, pas de la date de fin prévue.
    if was_active and subscription.expires_at is not None and subscription.expires_at > now:
        subscription.expires_at = max(now, subscription.started_at or now)
    subscription.cancel_reason = (reason or "").strip() or None
    await db.commit()
    if was_active:
        body = f"Votre abonnement {subscription.plan.name} a été arrêté par l'administration."
        if subscription.cancel_reason:
            body += f" Motif : {subscription.cancel_reason}."
        await _notify(db, subscription.vendor_id, "Abonnement arrêté", body)
    return subscription


async def admin_extend(db: AsyncSession, subscription_id: uuid.UUID, days: int) -> VendorSubscription:
    subscription = await _get(db, subscription_id)
    if subscription.status != SubscriptionStatus.ACTIVE or subscription.expires_at is None:
        raise ConflictError("Seul un abonnement actif peut être prolongé.")
    subscription.expires_at += timedelta(days=days)
    subscription.last_reminder_days = None
    # Une période programmée ensuite est décalée d'autant.
    later = await repository.get_scheduled(db, subscription.vendor_id, subscription.started_at)
    if later is not None and later.id != subscription.id:
        later.started_at += timedelta(days=days)
        later.expires_at += timedelta(days=days)
    await db.commit()
    await _notify(
        db,
        subscription.vendor_id,
        "Abonnement prolongé",
        f"Votre formule {subscription.plan.name} est prolongée de {days} jour{'s' if days > 1 else ''}, "
        f"jusqu'au {_date(subscription.expires_at)}.",
    )
    return subscription


async def admin_change_plan(db: AsyncSession, subscription_id: uuid.UUID, plan_id: uuid.UUID) -> VendorSubscription:
    subscription = await _get(db, subscription_id)
    if subscription.status not in (SubscriptionStatus.PENDING, SubscriptionStatus.ACTIVE):
        raise ConflictError("Cet abonnement est terminé.")
    plan = await _get_sellable_plan(db, plan_id, for_admin=True)
    subscription.plan_id = plan.id
    subscription.plan = plan
    await db.commit()
    if subscription.status == SubscriptionStatus.ACTIVE:
        await _notify(
            db, subscription.vendor_id, "Formule modifiée", f"Votre abonnement passe à la formule {plan.name}."
        )
    return subscription


async def grant_trial(
    db: AsyncSession, vendor_id: uuid.UUID, plan_id: uuid.UUID, days: int, *, automatic: bool = False
) -> VendorSubscription:
    vendor = await db.get(Vendor, vendor_id)
    if vendor is None:
        raise NotFoundError("Boutique introuvable.")
    plan = await _get_sellable_plan(db, plan_id, for_admin=True)
    if plan.id in await repository.trial_plan_ids(db, vendor.id):
        raise ConflictError(f"Cette boutique a déjà profité d'un essai de la formule {plan.name}.")
    now = quotas.now_utc()
    if await repository.latest_active_end(db, vendor.id, now) is not None:
        raise ConflictError("Cette boutique a déjà un abonnement en cours : l'essai n'aurait aucun effet.")

    subscription = await repository.create(
        db,
        vendor_id=vendor.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        is_trial=True,
        started_at=now,
        expires_at=now + timedelta(days=days),
    )
    subscription.plan = plan
    await db.commit()
    intro = "Bienvenue ! " if automatic else ""
    await _notify(
        db,
        vendor.id,
        f"Essai gratuit {plan.name} : {days} jours",
        f"{intro}Profitez de la formule {plan.name} gratuitement jusqu'au {_date(subscription.expires_at)} — "
        "sans engagement ni prélèvement.",
    )
    return subscription


async def maybe_auto_trial(db: AsyncSession, vendor: Vendor) -> None:
    """À l'approbation d'une boutique, si l'essai automatique est activé."""
    settings_row = await quotas.get_settings(db)
    if not settings_row.auto_trial_enabled or settings_row.auto_trial_plan_id is None:
        return
    try:
        await grant_trial(db, vendor.id, settings_row.auto_trial_plan_id, settings_row.auto_trial_days, automatic=True)
    except (ConflictError, NotFoundError):
        # Déjà essayé, abonnement en cours ou formule retirée : pas d'essai, sans bloquer l'approbation.
        await db.rollback()


async def admin_list(db: AsyncSession, status: SubscriptionStatus | None) -> list[AdminSubscriptionRead]:
    """Liste admin enrichie de la boutique, de son propriétaire et de ses produits en vente."""
    from app.catalog.models import Product, ProductStatus
    from app.users.models import User

    subscriptions = await repository.list_by_status(db, status)
    vendor_ids = {s.vendor_id for s in subscriptions}
    rows = (
        await db.execute(select(Vendor, User).join(User, User.id == Vendor.user_id).where(Vendor.id.in_(vendor_ids)))
    ).all() if vendor_ids else []
    owners = {vendor.id: (vendor, user) for vendor, user in rows}
    counts = dict(
        (
            await db.execute(
                select(Product.vendor_id, func.count())
                .where(Product.vendor_id.in_(vendor_ids), Product.status == ProductStatus.ACTIVE)
                .group_by(Product.vendor_id)
            )
        ).all()
    ) if vendor_ids else {}
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
                    "products_used": counts.get(sub.vendor_id, 0),
                }
            )
        )
    return result


async def admin_vendor_overview(db: AsyncSession, vendor_id: uuid.UUID) -> SubscriptionOverview:
    vendor = await db.get(Vendor, vendor_id)
    if vendor is None:
        raise NotFoundError("Boutique introuvable.")
    return await overview(db, vendor)


async def get_settings(db: AsyncSession) -> SubscriptionSettingsRead:
    row = await quotas.get_settings(db)
    await db.commit()
    return SubscriptionSettingsRead.model_validate(row)


async def update_settings(db: AsyncSession, data: SubscriptionSettingsUpdate) -> SubscriptionSettingsRead:
    row = await quotas.get_settings(db)
    fields = data.model_dump(exclude_unset=True)
    if fields.get("auto_trial_plan_id") is not None:
        await _get_sellable_plan(db, fields["auto_trial_plan_id"], for_admin=True)
    for name, value in fields.items():
        if value is None and name != "auto_trial_plan_id":
            continue
        setattr(row, name, value)
    await db.commit()
    return SubscriptionSettingsRead.model_validate(row)
