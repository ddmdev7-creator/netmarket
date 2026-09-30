"""Tâche périodique des abonnements (lancée par le lifespan de app/main.py) :
1. passe en EXPIRED les abonnements arrivés à échéance et prévient le vendeur ;
2. rappels avant la fin — essai : 3 jours puis 1 jour ; payé : 7 puis 1 —
   sauf si un renouvellement est déjà programmé ;
3. après la période de grâce, masque les produits au-delà du quota de la
   formule qui s'applique désormais (les plus récemment modifiés restent en
   vente). Rien n'est supprimé : le vendeur peut échanger lesquels restent.
"""

import asyncio
import logging
import math
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal
from app.subscriptions import quotas, repository
from app.subscriptions.models import SubscriptionStatus, VendorSubscription
from app.subscriptions.service import _notify

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 30 * 60
TRIAL_REMINDERS = (3, 1)
PAID_REMINDERS = (7, 1)


async def _expire(db: AsyncSession, now: datetime) -> int:
    ended = (
        (
            await db.execute(
                select(VendorSubscription)
                .where(VendorSubscription.status == SubscriptionStatus.ACTIVE, VendorSubscription.expires_at <= now)
                .options(selectinload(VendorSubscription.plan))
            )
        )
        .scalars()
        .all()
    )
    settings_row = await quotas.get_settings(db)
    for sub in ended:
        sub.status = SubscriptionStatus.EXPIRED
    await db.commit()
    for sub in ended:
        if await quotas.current_subscription(db, sub.vendor_id, now) is not None:
            continue  # un renouvellement a pris le relais
        free = await quotas.get_free_plan(db)
        what = "Votre essai" if sub.is_trial else "Votre abonnement"
        limit = f"{free.max_products} produits en vente" if free.max_products is not None else "ses quotas"
        await _notify(
            db,
            sub.vendor_id,
            f"{what} {sub.plan.name} est terminé",
            f"{what} {sub.plan.name} a pris fin. Vous repassez à la formule {free.name} ({limit}). "
            f"Vous avez {settings_row.grace_days} jours pour choisir les produits à garder en vente ou vous réabonner : "
            "ensuite, les produits en trop seront masqués (jamais supprimés).",
        )
    return len(ended)


async def _remind(db: AsyncSession, now: datetime) -> int:
    running = (
        (
            await db.execute(
                select(VendorSubscription)
                .where(
                    VendorSubscription.status == SubscriptionStatus.ACTIVE,
                    VendorSubscription.started_at <= now,
                    VendorSubscription.expires_at > now,
                )
                .options(selectinload(VendorSubscription.plan))
            )
        )
        .scalars()
        .all()
    )
    sent = 0
    for sub in running:
        days_left = math.ceil((sub.expires_at - now) / timedelta(days=1))
        thresholds = TRIAL_REMINDERS if sub.is_trial else PAID_REMINDERS
        due = [t for t in thresholds if days_left <= t and (sub.last_reminder_days is None or t < sub.last_reminder_days)]
        if not due:
            continue
        sub.last_reminder_days = min(due)
        await db.commit()
        if await repository.get_scheduled(db, sub.vendor_id, now) is not None:
            continue
        when = "demain" if days_left <= 1 else f"dans {days_left} jours"
        if sub.is_trial:
            title = f"Votre essai {sub.plan.name} se termine {when}"
            body = f"Pour garder les avantages de la formule {sub.plan.name}, abonnez-vous avant le {sub.expires_at:%d/%m/%Y}."
        else:
            title = f"Votre abonnement {sub.plan.name} se termine {when}"
            body = f"Renouvelez avant le {sub.expires_at:%d/%m/%Y} : la nouvelle période s'ajoutera à la suite, sans rien perdre."
        await _notify(db, sub.vendor_id, title, body, reminder=True)
        sent += 1
    return sent


async def _hide_excess(db: AsyncSession, now: datetime) -> int:
    from app.catalog.models import Product, ProductStatus

    settings_row = await quotas.get_settings(db)
    limit_date = now - timedelta(days=settings_row.grace_days)
    ended = (
        (
            await db.execute(
                select(VendorSubscription).where(
                    VendorSubscription.status.in_((SubscriptionStatus.EXPIRED, SubscriptionStatus.CANCELLED)),
                    VendorSubscription.grace_processed_at.is_(None),
                    VendorSubscription.started_at.is_not(None),
                    VendorSubscription.expires_at <= limit_date,
                )
            )
        )
        .scalars()
        .all()
    )
    hidden_total = 0
    for vendor_id in {s.vendor_id for s in ended}:
        for sub in ended:
            if sub.vendor_id == vendor_id:
                sub.grace_processed_at = now
        plan = (await quotas.entitlements(db, vendor_id)).plan
        hidden = 0
        if plan.max_products is not None:
            active = (
                (
                    await db.execute(
                        select(Product)
                        .where(Product.vendor_id == vendor_id, Product.status == ProductStatus.ACTIVE)
                        .order_by(Product.updated_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            for product in active[plan.max_products :]:
                product.status = ProductStatus.INACTIVE
                hidden += 1
        await db.commit()
        if hidden:
            hidden_total += hidden
            await _notify(
                db,
                vendor_id,
                f"{hidden} produit{'s' if hidden > 1 else ''} masqué{'s' if hidden > 1 else ''}",
                f"Votre formule {plan.name} permet {plan.max_products} produits en vente : les {hidden} en trop "
                "(les moins récemment modifiés) sont masqués, pas supprimés. Réabonnez-vous pour les remettre en vente, "
                "ou choisissez vous-même lesquels garder.",
            )
    return hidden_total


async def run_once(db: AsyncSession, *, now: datetime | None = None) -> None:
    now = now or quotas.now_utc()
    await _expire(db, now)
    await _remind(db, now)
    await _hide_excess(db, now)


async def run_forever() -> None:
    while True:
        # Laisse l'API finir de démarrer avant le premier passage.
        await asyncio.sleep(60)
        try:
            async with AsyncSessionLocal() as db:
                await run_once(db)
        except Exception:  # noqa: BLE001 - la boucle doit survivre à une erreur ponctuelle
            logger.exception("Échec de la tâche des abonnements")
        await asyncio.sleep(INTERVAL_SECONDS - 60)
