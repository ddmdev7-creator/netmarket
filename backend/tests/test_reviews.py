"""Tests for product reviews: gated on delivery, one per buyer, aggregated onto the product read."""

from httpx import AsyncClient

from app.catalog.models import Product
from app.couriers.models import Courier
from app.users.models import User
from tests.conftest import auth_headers

CHECKOUT_PAYLOAD = {"delivery_address": "Kaloum, près du marché", "payment_method": "cash_on_delivery"}


async def _buy_and_deliver(
    client: AsyncClient, buyer: User, vendor_user: User, product: Product, courier: Courier, courier_user: User
) -> None:
    add_response = await client.post(
        "/cart/items", json={"product_id": str(product.id), "quantity": 1}, headers=auth_headers(buyer)
    )
    assert add_response.status_code == 201

    checkout_response = await client.post("/orders/checkout", json=CHECKOUT_PAYLOAD, headers=auth_headers(buyer))
    sub_order_id = checkout_response.json()["sub_orders"][0]["id"]

    vendor_headers = auth_headers(vendor_user)
    await client.patch(
        f"/orders/sub-orders/{sub_order_id}/courier", json={"courier_id": str(courier.id)}, headers=vendor_headers
    )
    for target_status in ("confirmed", "preparing", "shipped"):
        step = await client.patch(
            f"/orders/sub-orders/{sub_order_id}/status", json={"status": target_status}, headers=vendor_headers
        )
        assert step.status_code == 200
    # La remise finale revient au livreur, pas au vendeur.
    delivered_step = await client.patch(
        f"/orders/sub-orders/{sub_order_id}/status",
        json={"status": "delivered"},
        headers=auth_headers(courier_user),
    )
    assert delivered_step.status_code == 200


async def test_review_requires_a_delivered_purchase(client: AsyncClient, buyer_user: User, product: Product) -> None:
    response = await client.post(
        f"/products/{product.id}/reviews", json={"rating": 5, "comment": "Top"}, headers=auth_headers(buyer_user)
    )

    assert response.status_code == 403


async def test_buyer_can_review_a_delivered_product(
    client: AsyncClient, buyer_user: User, vendor_user: User, product: Product, courier: Courier, courier_user: User
) -> None:
    await _buy_and_deliver(client, buyer_user, vendor_user, product, courier, courier_user)

    response = await client.post(
        f"/products/{product.id}/reviews", json={"rating": 4, "comment": "Bon produit"}, headers=auth_headers(buyer_user)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["rating"] == 4
    assert body["comment"] == "Bon produit"


async def test_buyer_cannot_review_the_same_product_twice(
    client: AsyncClient, buyer_user: User, vendor_user: User, product: Product, courier: Courier, courier_user: User
) -> None:
    await _buy_and_deliver(client, buyer_user, vendor_user, product, courier, courier_user)
    await client.post(f"/products/{product.id}/reviews", json={"rating": 5}, headers=auth_headers(buyer_user))

    response = await client.post(f"/products/{product.id}/reviews", json={"rating": 3}, headers=auth_headers(buyer_user))

    assert response.status_code == 409


async def test_rating_out_of_range_is_rejected(
    client: AsyncClient, buyer_user: User, vendor_user: User, product: Product, courier: Courier, courier_user: User
) -> None:
    await _buy_and_deliver(client, buyer_user, vendor_user, product, courier, courier_user)

    response = await client.post(f"/products/{product.id}/reviews", json={"rating": 6}, headers=auth_headers(buyer_user))

    assert response.status_code == 422


async def test_product_read_exposes_rating_summary(
    client: AsyncClient, buyer_user: User, vendor_user: User, product: Product, courier: Courier, courier_user: User
) -> None:
    # Pas encore d'avis : moyenne None, pas 0, pour ne pas afficher une fausse note de 0 étoile.
    fresh = await client.get(f"/products/{product.id}")
    assert fresh.json()["average_rating"] is None
    assert fresh.json()["review_count"] == 0

    await _buy_and_deliver(client, buyer_user, vendor_user, product, courier, courier_user)
    await client.post(f"/products/{product.id}/reviews", json={"rating": 4}, headers=auth_headers(buyer_user))

    detail = await client.get(f"/products/{product.id}")
    assert detail.json()["average_rating"] == 4
    assert detail.json()["review_count"] == 1

    list_response = await client.get(f"/products/{product.id}/reviews")
    assert len(list_response.json()) == 1


async def test_public_review_list_visible_without_auth(
    client: AsyncClient, buyer_user: User, vendor_user: User, product: Product, courier: Courier, courier_user: User
) -> None:
    await _buy_and_deliver(client, buyer_user, vendor_user, product, courier, courier_user)
    await client.post(f"/products/{product.id}/reviews", json={"rating": 5}, headers=auth_headers(buyer_user))

    response = await client.get(f"/products/{product.id}/reviews")

    assert response.status_code == 200
    assert response.json()[0]["rating"] == 5


async def test_reviewable_products_lists_delivered_products_with_my_review(
    client: AsyncClient, buyer_user: User, vendor_user: User, product: Product, courier: Courier, courier_user: User
) -> None:
    empty = await client.get("/reviews/mine", headers=auth_headers(buyer_user))
    assert empty.status_code == 200
    assert empty.json() == []

    await _buy_and_deliver(client, buyer_user, vendor_user, product, courier, courier_user)

    [pending] = (await client.get("/reviews/mine", headers=auth_headers(buyer_user))).json()
    assert pending["product_id"] == str(product.id)
    assert pending["review"] is None

    await client.post(f"/products/{product.id}/reviews", json={"rating": 3}, headers=auth_headers(buyer_user))

    [reviewed] = (await client.get("/reviews/mine", headers=auth_headers(buyer_user))).json()
    assert reviewed["review"]["rating"] == 3


async def test_buyer_can_update_own_review(
    client: AsyncClient, buyer_user: User, vendor_user: User, product: Product, courier: Courier, courier_user: User
) -> None:
    await _buy_and_deliver(client, buyer_user, vendor_user, product, courier, courier_user)
    await client.post(f"/products/{product.id}/reviews", json={"rating": 2}, headers=auth_headers(buyer_user))

    response = await client.put(
        f"/products/{product.id}/reviews/mine",
        json={"rating": 5, "comment": "Finalement très bien"},
        headers=auth_headers(buyer_user),
    )

    assert response.status_code == 200
    assert response.json()["rating"] == 5
    [listed] = (await client.get(f"/products/{product.id}/reviews")).json()
    assert (listed["rating"], listed["comment"]) == (5, "Finalement très bien")


async def test_updating_a_missing_review_is_404(client: AsyncClient, buyer_user: User, product: Product) -> None:
    response = await client.put(
        f"/products/{product.id}/reviews/mine", json={"rating": 5}, headers=auth_headers(buyer_user)
    )

    assert response.status_code == 404


async def test_review_list_shows_first_name_and_initial_only(
    client: AsyncClient,
    db_session,
    buyer_user: User,
    vendor_user: User,
    product: Product,
    courier: Courier,
    courier_user: User,
) -> None:
    buyer_user.first_name, buyer_user.last_name = "Mamadou", "Diallo"
    await db_session.flush()
    await _buy_and_deliver(client, buyer_user, vendor_user, product, courier, courier_user)
    await client.post(f"/products/{product.id}/reviews", json={"rating": 4}, headers=auth_headers(buyer_user))

    [listed] = (await client.get(f"/products/{product.id}/reviews")).json()

    assert listed["author_name"] == "Mamadou D."
