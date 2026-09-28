"""Favoris, alertes prix/stock et rappel de panier."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.cart.models import CartItem
from app.cart.reminders import send_cart_reminders
from app.catalog.models import Product
from app.notifications.models import Notification, NotificationType
from app.users.models import User
from tests.conftest import auth_headers


async def _notifications(db: AsyncSession, user: User) -> list[Notification]:
    return list((await db.execute(select(Notification).where(Notification.user_id == user.id))).scalars().all())


async def test_add_list_and_remove_favorite(client: AsyncClient, buyer_user: User, product: Product) -> None:
    headers = auth_headers(buyer_user)
    assert (await client.put(f"/favorites/{product.id}", headers=headers)).status_code == 200
    # Idempotent.
    assert (await client.put(f"/favorites/{product.id}", headers=headers)).status_code == 200

    assert (await client.get("/favorites/ids", headers=headers)).json() == {"product_ids": [str(product.id)]}
    listed = (await client.get("/favorites", headers=headers)).json()
    assert listed[0]["product"]["id"] == str(product.id) and listed[0]["price_at_add"] == 500000

    assert (await client.delete(f"/favorites/{product.id}", headers=headers)).status_code == 200
    assert (await client.get("/favorites/ids", headers=headers)).json() == {"product_ids": []}


async def test_favorites_require_login(client: AsyncClient, product: Product) -> None:
    assert (await client.put(f"/favorites/{product.id}")).status_code == 401


async def test_price_drop_alerts_once_per_new_low(
    client: AsyncClient, db_session: AsyncSession, buyer_user: User, vendor_user: User, product: Product
) -> None:
    await client.put(f"/favorites/{product.id}", headers=auth_headers(buyer_user))
    vendor = auth_headers(vendor_user)

    await client.patch(f"/products/{product.id}", json={"price": 450000}, headers=vendor)
    await client.patch(f"/products/{product.id}", json={"price": 470000}, headers=vendor)  # remonte : rien
    await client.patch(f"/products/{product.id}", json={"price": 460000}, headers=vendor)  # sous 470k mais pas sous 450k : rien
    await client.patch(f"/products/{product.id}", json={"price": 400000}, headers=vendor)

    alerts = [n for n in await _notifications(db_session, buyer_user) if n.type == NotificationType.FAVORITE_PRICE_DROP]
    assert len(alerts) == 2
    assert all(n.product_id == product.id for n in alerts)


async def test_back_in_stock_alert(
    client: AsyncClient, db_session: AsyncSession, buyer_user: User, vendor_user: User, product: Product
) -> None:
    vendor = auth_headers(vendor_user)
    await client.patch(f"/products/{product.id}", json={"stock": 0}, headers=vendor)
    await client.put(f"/favorites/{product.id}", headers=auth_headers(buyer_user))

    await client.patch(f"/products/{product.id}", json={"stock": 3}, headers=vendor)

    types = [n.type for n in await _notifications(db_session, buyer_user)]
    assert types == [NotificationType.FAVORITE_BACK_IN_STOCK]
    body = (await client.get("/notifications", headers=auth_headers(buyer_user))).json()
    assert body["items"][0]["product_id"] == str(product.id)


async def test_cart_reminder_sent_once_per_cart_state(
    client: AsyncClient, db_session: AsyncSession, buyer_user: User, product: Product
) -> None:
    await client.post("/cart/items", json={"product_id": str(product.id), "quantity": 2}, headers=auth_headers(buyer_user))
    now = datetime.now(UTC)

    # Panier trop récent : pas encore de rappel.
    assert await send_cart_reminders(db_session, now=now) == 0

    await db_session.execute(update(CartItem).values(updated_at=now - timedelta(hours=30)))
    assert await send_cart_reminders(db_session, now=now) == 1
    assert await send_cart_reminders(db_session, now=now) == 0

    reminders = [n for n in await _notifications(db_session, buyer_user) if n.type == NotificationType.CART_REMINDER]
    assert len(reminders) == 1 and "2 articles" in reminders[0].body
