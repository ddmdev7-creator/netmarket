"""Tests for admin account management: GET/DELETE /admin/users.

The delete endpoint has to cascade across almost every module (a user can be
a vendor with a shop, a buyer with order history, a courier mid-dispatch,
etc.) — these tests exercise the real checkout flow to build that data
first, then check the cascade removes everything belonging to the deleted
account without leaving orphaned rows or violating a foreign key, while
leaving unrelated accounts (and, when deleting a vendor, other buyers'
order history) untouched.
"""

import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.addresses.models import Address
from app.cart.models import CartItem
from app.catalog.models import Product
from app.core.security import verify_password
from app.couriers.models import Courier
from app.orders.models import Order, OrderItem, SubOrder
from app.payments.models import Payment
from app.pickup_point_managers.models import PickupPointManager
from app.reviews.models import Review
from app.subscriptions.models import SubscriptionPlan, VendorSubscription
from app.users.models import User, UserRole
from app.vendors.models import Vendor
from tests.conftest import auth_headers, make_user

CHECKOUT_PAYLOAD = {"delivery_address": "Kaloum, près du marché", "payment_method": "cash_on_delivery"}


async def _checkout(client: AsyncClient, buyer: User, product: Product) -> dict:
    add_response = await client.post(
        "/cart/items", json={"product_id": str(product.id), "quantity": 1}, headers=auth_headers(buyer)
    )
    assert add_response.status_code == 201
    checkout_response = await client.post("/orders/checkout", json=CHECKOUT_PAYLOAD, headers=auth_headers(buyer))
    assert checkout_response.status_code == 201
    return checkout_response.json()


async def test_non_admin_cannot_list_or_delete_users(client: AsyncClient, buyer_user: User) -> None:
    list_response = await client.get("/admin/users", headers=auth_headers(buyer_user))
    delete_response = await client.delete(f"/admin/users/{buyer_user.id}", headers=auth_headers(buyer_user))

    assert list_response.status_code == 403
    assert delete_response.status_code == 403


async def test_admin_can_list_users(client: AsyncClient, admin_user: User, buyer_user: User) -> None:
    response = await client.get("/admin/users", headers=auth_headers(admin_user))

    assert response.status_code == 200
    ids = {row["id"] for row in response.json()}
    assert str(admin_user.id) in ids
    assert str(buyer_user.id) in ids


async def test_admin_cannot_delete_own_account(client: AsyncClient, admin_user: User) -> None:
    response = await client.delete(f"/admin/users/{admin_user.id}", headers=auth_headers(admin_user))

    assert response.status_code == 403


async def test_admin_cannot_delete_another_admin(
    client: AsyncClient, admin_user: User, db_session: AsyncSession
) -> None:
    other_admin = await make_user(db_session, phone="+224620000099", role=UserRole.ADMIN)

    response = await client.delete(f"/admin/users/{other_admin.id}", headers=auth_headers(admin_user))

    assert response.status_code == 403


async def test_delete_unknown_user_is_404(client: AsyncClient, admin_user: User) -> None:
    response = await client.delete(f"/admin/users/{uuid.uuid4()}", headers=auth_headers(admin_user))

    assert response.status_code == 404


async def test_deleting_a_buyer_cascades_but_keeps_vendor_and_product(
    client: AsyncClient,
    admin_user: User,
    buyer_user: User,
    vendor_user: User,
    vendor: Vendor,
    product: Product,
    db_session: AsyncSession,
) -> None:
    order = await _checkout(client, buyer_user, product)
    order_id = uuid.UUID(order["id"])
    sub_order_id = uuid.UUID(order["sub_orders"][0]["id"])

    # Leftover cart item never checked out, plus an address and a review —
    # inserted directly since the point here is the cascade, not re-testing
    # cart/address/review business rules already covered elsewhere.
    db_session.add(CartItem(user_id=buyer_user.id, product_id=product.id, quantity=1))
    db_session.add(Address(user_id=buyer_user.id, label="Maison", zone="Kaloum"))
    db_session.add(Review(product_id=product.id, user_id=buyer_user.id, rating=5, comment="Top"))
    await db_session.flush()

    response = await client.delete(f"/admin/users/{buyer_user.id}", headers=auth_headers(admin_user))
    assert response.status_code == 200

    assert (await db_session.execute(select(User).where(User.id == buyer_user.id))).scalar_one_or_none() is None
    assert (await db_session.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none() is None
    assert (
        await db_session.execute(select(SubOrder).where(SubOrder.id == sub_order_id))
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(select(OrderItem).where(OrderItem.sub_order_id == sub_order_id))
    ).scalar_one_or_none() is None
    assert (await db_session.execute(select(Payment).where(Payment.order_id == order_id))).scalar_one_or_none() is None
    assert (
        await db_session.execute(select(CartItem).where(CartItem.user_id == buyer_user.id))
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(select(Address).where(Address.user_id == buyer_user.id))
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(select(Review).where(Review.user_id == buyer_user.id))
    ).scalar_one_or_none() is None

    # The vendor and product must survive a buyer's deletion untouched.
    assert (await db_session.execute(select(Vendor).where(Vendor.id == vendor.id))).scalar_one_or_none() is not None
    assert (await db_session.execute(select(Product).where(Product.id == product.id))).scalar_one_or_none() is not None


async def test_deleting_a_vendor_removes_shop_but_keeps_buyer_and_order(
    client: AsyncClient,
    admin_user: User,
    buyer_user: User,
    vendor_user: User,
    vendor: Vendor,
    product: Product,
    subscription_plan: SubscriptionPlan,
    db_session: AsyncSession,
) -> None:
    order = await _checkout(client, buyer_user, product)
    order_id = uuid.UUID(order["id"])
    sub_order_id = uuid.UUID(order["sub_orders"][0]["id"])

    db_session.add(Review(product_id=product.id, user_id=buyer_user.id, rating=4, comment="Bien"))
    db_session.add(VendorSubscription(vendor_id=vendor.id, plan_id=subscription_plan.id))
    await db_session.flush()
    # Cart item added after checkout (checkout empties the cart), so there's
    # a leftover row on this vendor's product to prove the cascade reaches
    # cart items owned by a *different* user than the one being deleted.
    db_session.add(CartItem(user_id=buyer_user.id, product_id=product.id, quantity=2))
    await db_session.flush()

    response = await client.delete(f"/admin/users/{vendor_user.id}", headers=auth_headers(admin_user))
    assert response.status_code == 200

    assert (await db_session.execute(select(User).where(User.id == vendor_user.id))).scalar_one_or_none() is None
    assert (await db_session.execute(select(Vendor).where(Vendor.id == vendor.id))).scalar_one_or_none() is None
    assert (await db_session.execute(select(Product).where(Product.id == product.id))).scalar_one_or_none() is None
    assert (
        await db_session.execute(select(VendorSubscription).where(VendorSubscription.vendor_id == vendor.id))
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(select(Review).where(Review.product_id == product.id))
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(select(CartItem).where(CartItem.product_id == product.id))
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(select(SubOrder).where(SubOrder.id == sub_order_id))
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(select(OrderItem).where(OrderItem.sub_order_id == sub_order_id))
    ).scalar_one_or_none() is None

    # The buyer and their order (now with zero sub-orders) survive a vendor's deletion.
    assert (await db_session.execute(select(User).where(User.id == buyer_user.id))).scalar_one_or_none() is not None
    assert (await db_session.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none() is not None
    assert (await db_session.execute(select(Payment).where(Payment.order_id == order_id))).scalar_one_or_none() is not None


async def test_deleting_a_courier_succeeds(
    client: AsyncClient, admin_user: User, courier_user: User, courier: Courier, db_session: AsyncSession
) -> None:
    response = await client.delete(f"/admin/users/{courier_user.id}", headers=auth_headers(admin_user))

    assert response.status_code == 200
    assert (await db_session.execute(select(Courier).where(Courier.id == courier.id))).scalar_one_or_none() is None


async def test_deleting_a_pickup_point_manager_keeps_the_pickup_point(
    client: AsyncClient,
    admin_user: User,
    manager_user: User,
    manager: PickupPointManager,
    pickup_point,
    db_session: AsyncSession,
) -> None:
    response = await client.delete(f"/admin/users/{manager_user.id}", headers=auth_headers(admin_user))

    assert response.status_code == 200
    assert (
        await db_session.execute(select(PickupPointManager).where(PickupPointManager.id == manager.id))
    ).scalar_one_or_none() is None


async def test_admin_can_reset_a_users_password(
    client: AsyncClient, admin_user: User, buyer_user: User, db_session: AsyncSession
) -> None:
    response = await client.patch(
        f"/admin/users/{buyer_user.id}/password",
        json={"new_password": "NouveauMotDePasse1"},
        headers=auth_headers(admin_user),
    )

    assert response.status_code == 200
    await db_session.refresh(buyer_user)
    assert verify_password("NouveauMotDePasse1", buyer_user.password_hash)


async def test_reset_password_rejects_short_password(
    client: AsyncClient, admin_user: User, buyer_user: User
) -> None:
    response = await client.patch(
        f"/admin/users/{buyer_user.id}/password", json={"new_password": "short"}, headers=auth_headers(admin_user)
    )

    assert response.status_code == 422


async def test_non_admin_cannot_reset_a_password(client: AsyncClient, buyer_user: User) -> None:
    response = await client.patch(
        f"/admin/users/{buyer_user.id}/password",
        json={"new_password": "NouveauMotDePasse1"},
        headers=auth_headers(buyer_user),
    )

    assert response.status_code == 403


async def test_reset_password_for_unknown_user_is_404(client: AsyncClient, admin_user: User) -> None:
    response = await client.patch(
        f"/admin/users/{uuid.uuid4()}/password",
        json={"new_password": "NouveauMotDePasse1"},
        headers=auth_headers(admin_user),
    )

    assert response.status_code == 404
