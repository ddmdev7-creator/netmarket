"""Shared pytest fixtures.

Tests run against a real PostgreSQL database (TEST_DATABASE_URL) so that
Postgres-specific types used by the models (UUID, ARRAY, native ENUM) behave
exactly as in production. Each test runs inside a SAVEPOINT that is rolled
back afterwards, so tests are isolated from each other even though the
application code calls commit().
"""

import os
import uuid
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.addresses.models import Address  # noqa: F401
from app.cart.models import CartItem  # noqa: F401
from app.catalog.models import Category, Product, ProductStatus
from app.couriers.models import Courier, CourierStatus, VehicleType
from app.core.database import Base
from app.core.deps import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.orders.models import Order, OrderItem, SubOrder  # noqa: F401
from app.payments.models import Payment  # noqa: F401
from app.pickup_point_managers.models import PickupPointManager  # noqa: F401
from app.pickup_points.models import PickupPoint  # noqa: F401
from app.reviews.models import Review  # noqa: F401
from app.subscriptions.models import SubscriptionPlan
from app.users.models import User, UserRole
from app.vendors.models import Vendor, VendorStatus
from app.wallets.models import LedgerAccount  # noqa: F401

try:
    TEST_DATABASE_URL = os.environ["TEST_DATABASE_URL"]
except KeyError as exc:
    # No fallback to DATABASE_URL: _prepare_database below does a drop_all/
    # create_all, which would silently wipe whatever database DATABASE_URL
    # points at (including production, in an environment where only
    # DATABASE_URL happens to be set) the first time someone runs pytest there.
    raise RuntimeError(
        "TEST_DATABASE_URL doit être défini pour lancer les tests — jamais de repli "
        "sur DATABASE_URL, qui pointerait vers une vraie base (dev ou prod) que "
        "_prepare_database détruirait (drop_all/create_all)."
    ) from exc


# NullPool: each checkout opens a fresh asyncpg connection and closes it on
# release, instead of pooling connections across pytest-asyncio's per-test
# event loops (asyncpg connections are bound to the loop that created them).
engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _prepare_database() -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    connection = await engine.connect()
    outer_transaction = await connection.begin()
    session = AsyncSession(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()
        await outer_transaction.rollback()
        await connection.close()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def make_user(db_session: AsyncSession, *, phone: str, role: UserRole) -> User:
    user = User(phone=phone, password_hash=hash_password("password123"), role=role)
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def buyer_user(db_session: AsyncSession) -> User:
    return await make_user(db_session, phone="+224620000001", role=UserRole.BUYER)


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    return await make_user(db_session, phone="+224620000002", role=UserRole.ADMIN)


@pytest_asyncio.fixture
async def vendor_user(db_session: AsyncSession) -> User:
    user = await make_user(db_session, phone="+224620000003", role=UserRole.VENDOR)
    vendor = Vendor(user_id=user.id, shop_name="Boutique Test", status=VendorStatus.APPROVED)
    db_session.add(vendor)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def unapproved_vendor_user(db_session: AsyncSession) -> User:
    user = await make_user(db_session, phone="+224620000004", role=UserRole.VENDOR)
    vendor = Vendor(user_id=user.id, shop_name="Boutique En Attente", status=VendorStatus.PENDING)
    db_session.add(vendor)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def category(db_session: AsyncSession) -> Category:
    cat = Category(name="Électronique")
    db_session.add(cat)
    await db_session.flush()
    return cat


@pytest_asyncio.fixture
async def vendor(db_session: AsyncSession, vendor_user: User) -> Vendor:
    result = await db_session.execute(select(Vendor).where(Vendor.user_id == vendor_user.id))
    return result.scalar_one()


@pytest_asyncio.fixture
async def product(db_session: AsyncSession, vendor: Vendor, category: Category) -> Product:
    item = Product(vendor_id=vendor.id, category_id=category.id, name="Téléphone", price=500000, stock=10)
    db_session.add(item)
    await db_session.flush()
    return item


@pytest_asyncio.fixture
async def subscription_plan(db_session: AsyncSession) -> SubscriptionPlan:
    plan = SubscriptionPlan(name="Premium mensuel", price_gnf=20000, duration_days=30)
    db_session.add(plan)
    await db_session.flush()
    return plan


async def make_vendor(db_session: AsyncSession, *, phone: str, shop_name: str) -> tuple[User, Vendor]:
    user = await make_user(db_session, phone=phone, role=UserRole.VENDOR)
    vendor_row = Vendor(user_id=user.id, shop_name=shop_name, status=VendorStatus.APPROVED)
    db_session.add(vendor_row)
    await db_session.flush()
    return user, vendor_row


@pytest_asyncio.fixture
async def courier_user(db_session: AsyncSession) -> User:
    user = await make_user(db_session, phone="+224620000005", role=UserRole.COURIER)
    courier = Courier(user_id=user.id, vehicle_type=VehicleType.MOTO, status=CourierStatus.APPROVED)
    db_session.add(courier)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def courier(db_session: AsyncSession, courier_user: User) -> Courier:
    result = await db_session.execute(select(Courier).where(Courier.user_id == courier_user.id))
    return result.scalar_one()


@pytest_asyncio.fixture
async def pickup_point(db_session: AsyncSession) -> PickupPoint:
    point = PickupPoint(name="Point Test", zone="Kaloum")
    db_session.add(point)
    await db_session.flush()
    return point


@pytest_asyncio.fixture
async def manager_user(db_session: AsyncSession, pickup_point: PickupPoint) -> User:
    user = await make_user(db_session, phone="+224620000006", role=UserRole.PICKUP_POINT_MANAGER)
    manager = PickupPointManager(user_id=user.id, pickup_point_id=pickup_point.id)
    db_session.add(manager)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def manager(db_session: AsyncSession, manager_user: User) -> PickupPointManager:
    result = await db_session.execute(select(PickupPointManager).where(PickupPointManager.user_id == manager_user.id))
    return result.scalar_one()


def auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


async def scan_handoff(client: AsyncClient, scanner: User, sub_order_id):
    """Remise d'un colis comme en vrai : calcule le QR affiché à cette étape
    (celui du client, ou du livreur au dépôt — voir app/orders/handoff.py)
    et le fait scanner par `scanner` via POST /orders/sub-orders/confirm-delivery."""
    from app.orders import handoff

    session = await anext(app.dependency_overrides[get_db]())
    sub_order = await session.get(SubOrder, uuid.UUID(str(sub_order_id)))
    await session.refresh(sub_order)
    handoff.ensure_stage_nonce(sub_order)
    await session.flush()
    code, _ = handoff.current_code(sub_order)
    return await client.post(
        "/orders/sub-orders/confirm-delivery", json={"code": code}, headers=auth_headers(scanner)
    )
