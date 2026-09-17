"""Vendor onboarding, own-profile management, public directory and admin validation."""

import uuid
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import repository as catalog_repository
from app.catalog.repository import LOW_STOCK_THRESHOLD
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.orders import repository as orders_repository
from app.users import repository as user_repository
from app.users import service as user_service
from app.users.models import User, UserRole
from app.vendors import repository
from app.vendors.models import Vendor, VendorStatus
from app.vendors.schemas import (
    DailyOrderCount,
    LowStockProduct,
    VendorAdminUpdate,
    VendorDashboard,
    VendorOwnerUpdate,
    VendorRegister,
)

ORDERS_TIMESERIES_DAYS = 14


async def register_vendor(db: AsyncSession, user: User, data: VendorRegister) -> Vendor:
    # Un compte admin ne peut jamais accéder à /vendeur/* (gate par role == "vendor"
    # exact côté frontend et require_role côté API) : le laisser créer une boutique
    # produirait une Vendor orpheline, inaccessible pour toujours. Seuls les
    # acheteurs peuvent devenir vendeurs (promotion ci-dessous).
    if user.role == UserRole.ADMIN:
        raise ForbiddenError("Un compte administrateur ne peut pas créer de boutique.")

    if await repository.get_by_user_id(db, user.id) is not None:
        raise ConflictError("Vous avez déjà une boutique enregistrée.")

    if data.email != user.email:
        existing = await user_repository.get_by_email(db, data.email)
        if existing is not None and existing.id != user.id:
            raise ConflictError("Cet email est déjà utilisé.")
        user.email = data.email
        # New/changed email starts unverified even if the old one was —
        # access to the dashboard is gated on this, see middleware/vendor.ts.
        user.email_verified = False

    vendor = await repository.create(
        db,
        user_id=user.id,
        shop_name=data.shop_name,
        zone=data.zone,
        latitude=data.latitude,
        longitude=data.longitude,
    )

    # La boutique doit encore être validée par un administrateur, mais le
    # rôle change dès l'inscription pour donner accès au tableau de bord vendeur.
    if user.role == UserRole.BUYER:
        user.role = UserRole.VENDOR

    await db.commit()
    await db.refresh(vendor)

    if not user.email_verified:
        await user_service.send_verification_code(db, user)

    return vendor


async def get_my_vendor(db: AsyncSession, user: User) -> Vendor:
    vendor = await repository.get_by_user_id(db, user.id)
    if vendor is None:
        raise NotFoundError("Vous n'avez pas encore de boutique. Veuillez d'abord vous inscrire comme vendeur.")
    return vendor


async def update_my_vendor(db: AsyncSession, user: User, data: VendorOwnerUpdate) -> Vendor:
    vendor = await get_my_vendor(db, user)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(vendor, field, value)
    await db.commit()
    await db.refresh(vendor)
    return vendor


async def get_public_vendor(db: AsyncSession, vendor_id: uuid.UUID) -> Vendor:
    vendor = await repository.get_by_id(db, vendor_id)
    if vendor is None or vendor.status != VendorStatus.APPROVED:
        raise NotFoundError("Boutique introuvable.")
    return vendor


async def list_public_vendors(db: AsyncSession) -> list[Vendor]:
    return await repository.list_by_status(db, VendorStatus.APPROVED)


async def admin_list_vendors(db: AsyncSession, status: VendorStatus | None) -> list[Vendor]:
    return await repository.list_by_status(db, status)


async def admin_update_vendor(db: AsyncSession, vendor_id: uuid.UUID, data: VendorAdminUpdate) -> Vendor:
    vendor = await repository.get_by_id(db, vendor_id)
    if vendor is None:
        raise NotFoundError("Boutique introuvable.")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(vendor, field, value)
    await db.commit()
    await db.refresh(vendor)
    return vendor


async def get_my_dashboard(db: AsyncSession, user: User) -> VendorDashboard:
    vendor = await get_my_vendor(db, user)

    counts = await orders_repository.get_vendor_dashboard_counts(db, vendor.id)
    status_counts = counts["status_counts"]
    active_orders = status_counts["pending"] + status_counts["confirmed"] + status_counts["preparing"] + status_counts["shipped"]

    active_product_count = await catalog_repository.count_active_products_for_vendor(db, vendor.id)
    # Un seul appel (stock <= seuil) couvre les deux cas — on sépare juste
    # stock == 0 (rupture) du reste (stock faible) après coup, pour ne pas
    # lister deux fois le même produit dans les deux sections.
    low_stock = await catalog_repository.list_low_stock_products(db, vendor.id, LOW_STOCK_THRESHOLD)
    out_of_stock = [p for p in low_stock if p.stock == 0]
    low_stock = [p for p in low_stock if p.stock > 0]

    return VendorDashboard(
        total_orders=sum(status_counts.values()),
        active_orders=active_orders,
        delivered_orders=status_counts["delivered"],
        cancelled_orders=status_counts["cancelled"],
        revenue_delivered=counts["revenue_delivered"],
        commission_due=counts["commission_due"],
        net_revenue=counts["revenue_delivered"] - counts["commission_due"],
        active_product_count=active_product_count,
        low_stock_products=[LowStockProduct.model_validate(p) for p in low_stock],
        out_of_stock_products=[LowStockProduct.model_validate(p) for p in out_of_stock],
    )


async def get_my_orders_timeseries(db: AsyncSession, user: User) -> list[DailyOrderCount]:
    vendor = await get_my_vendor(db, user)
    counts = await orders_repository.get_daily_order_counts(db, vendor.id, ORDERS_TIMESERIES_DAYS)

    since = date.today() - timedelta(days=ORDERS_TIMESERIES_DAYS - 1)
    return [
        DailyOrderCount(day=since + timedelta(days=i), order_count=counts.get(since + timedelta(days=i), 0))
        for i in range(ORDERS_TIMESERIES_DAYS)
    ]
