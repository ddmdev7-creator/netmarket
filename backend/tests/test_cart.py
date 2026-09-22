"""Tests for the cart: add/update/remove, vendor grouping, ownership."""

import uuid
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Category, Product
from app.users.models import User
from app.vendors.models import Vendor
from tests.conftest import auth_headers, make_vendor


async def test_add_item_creates_entry_grouped_by_vendor(
    client: AsyncClient, buyer_user: User, product: Product
) -> None:
    response = await client.post(
        "/cart/items", json={"product_id": str(product.id), "quantity": 2}, headers=auth_headers(buyer_user)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["total"] == product.price * 2
    assert len(body["vendors"]) == 1
    assert body["vendors"][0]["items"][0]["quantity"] == 2


async def test_add_same_product_twice_increments_quantity(
    client: AsyncClient, buyer_user: User, product: Product
) -> None:
    headers = auth_headers(buyer_user)
    await client.post("/cart/items", json={"product_id": str(product.id), "quantity": 1}, headers=headers)

    response = await client.post("/cart/items", json={"product_id": str(product.id), "quantity": 2}, headers=headers)

    body = response.json()
    assert body["vendors"][0]["items"][0]["quantity"] == 3


async def test_update_and_remove_item(client: AsyncClient, buyer_user: User, product: Product) -> None:
    headers = auth_headers(buyer_user)
    add_response = await client.post(
        "/cart/items", json={"product_id": str(product.id), "quantity": 1}, headers=headers
    )
    item_id = add_response.json()["vendors"][0]["items"][0]["id"]

    update_response = await client.patch(f"/cart/items/{item_id}", json={"quantity": 5}, headers=headers)
    assert update_response.json()["vendors"][0]["items"][0]["quantity"] == 5

    remove_response = await client.delete(f"/cart/items/{item_id}", headers=headers)
    assert remove_response.json()["vendors"] == []


async def test_add_inactive_product_fails(client: AsyncClient, vendor_user: User, buyer_user: User, product: Product) -> None:
    await client.patch(
        f"/products/{product.id}", json={"status": "inactive"}, headers=auth_headers(vendor_user)
    )

    response = await client.post(
        "/cart/items", json={"product_id": str(product.id), "quantity": 1}, headers=auth_headers(buyer_user)
    )

    assert response.status_code == 409


async def test_cart_item_ownership_is_enforced(
    client: AsyncClient, db_session: AsyncSession, buyer_user: User, product: Product
) -> None:
    add_response = await client.post(
        "/cart/items", json={"product_id": str(product.id), "quantity": 1}, headers=auth_headers(buyer_user)
    )
    item_id = add_response.json()["vendors"][0]["items"][0]["id"]

    other_user, _ = await make_vendor(db_session, phone="+224620008888", shop_name="Autre")
    response = await client.patch(f"/cart/items/{item_id}", json={"quantity": 2}, headers=auth_headers(other_user))

    assert response.status_code == 403


async def test_cart_groups_multiple_vendors(
    client: AsyncClient, db_session: AsyncSession, buyer_user: User, product: Product, category: Category
) -> None:
    _, other_vendor = await make_vendor(db_session, phone="+224620007777", shop_name="Deuxième Boutique")
    other_product = Product(vendor_id=other_vendor.id, category_id=category.id, name="Casque", price=100000, stock=5)
    db_session.add(other_product)
    await db_session.flush()

    headers = auth_headers(buyer_user)
    await client.post("/cart/items", json={"product_id": str(product.id), "quantity": 1}, headers=headers)
    response = await client.post(
        "/cart/items", json={"product_id": str(other_product.id), "quantity": 1}, headers=headers
    )

    assert len(response.json()["vendors"]) == 2


# --- Cart with product variants ---


async def test_add_item_with_variant_id_sets_variant_label_and_price_override(
    client: AsyncClient, db_session: AsyncSession, vendor_user: User, buyer_user: User, product: Product
) -> None:
    variant = (
        await client.post(
            f"/products/{product.id}/variants",
            json={"attributes": [{"name": "Couleur", "value": "Rouge"}], "price": 600000, "stock": 5},
            headers=auth_headers(vendor_user),
        )
    ).json()
    # Product.variants a été chargée (vide) par l'appel ci-dessus, dans la
    # même session de test partagée entre requêtes — sans ce rafraîchissement
    # ciblé, elle resterait figée à vide (une vraie requête HTTP séparée en
    # production n'a pas ce souci, chaque requête ouvrant sa propre session).
    # expire_all() serait trop large ici : ça périmerait aussi vendor_user
    # etc., dont l'accès synchrone ensuite (hors contexte async) ferait
    # planter SQLAlchemy.
    await db_session.refresh(product, attribute_names=["variants"])

    response = await client.post(
        "/cart/items",
        json={"product_id": str(product.id), "variant_id": variant["id"], "quantity": 2},
        headers=auth_headers(buyer_user),
    )

    assert response.status_code == 201
    item = response.json()["vendors"][0]["items"][0]
    assert item["variant_label"] == "Couleur : Rouge"
    assert item["unit_price"] == 600000
    assert item["subtotal"] == 1200000


async def test_add_same_variant_twice_increments_quantity(
    client: AsyncClient, db_session: AsyncSession, vendor_user: User, buyer_user: User, product: Product
) -> None:
    variant = (
        await client.post(
            f"/products/{product.id}/variants",
            json={"attributes": [{"name": "Taille", "value": "M"}], "stock": 5},
            headers=auth_headers(vendor_user),
        )
    ).json()
    await db_session.refresh(product, attribute_names=["variants"])  # voir le commentaire équivalent plus haut
    headers = auth_headers(buyer_user)

    await client.post(
        "/cart/items",
        json={"product_id": str(product.id), "variant_id": variant["id"], "quantity": 1},
        headers=headers,
    )
    response = await client.post(
        "/cart/items",
        json={"product_id": str(product.id), "variant_id": variant["id"], "quantity": 2},
        headers=headers,
    )

    assert response.json()["vendors"][0]["items"][0]["quantity"] == 3


async def test_add_different_variants_of_same_product_creates_separate_rows(
    client: AsyncClient, db_session: AsyncSession, vendor_user: User, buyer_user: User, product: Product
) -> None:
    headers_vendor = auth_headers(vendor_user)
    v1 = (
        await client.post(
            f"/products/{product.id}/variants",
            json={"attributes": [{"name": "Taille", "value": "S"}], "stock": 5},
            headers=headers_vendor,
        )
    ).json()
    v2 = (
        await client.post(
            f"/products/{product.id}/variants",
            json={"attributes": [{"name": "Taille", "value": "L"}], "stock": 5},
            headers=headers_vendor,
        )
    ).json()
    await db_session.refresh(product, attribute_names=["variants"])  # voir le commentaire équivalent plus haut

    headers = auth_headers(buyer_user)
    await client.post(
        "/cart/items", json={"product_id": str(product.id), "variant_id": v1["id"], "quantity": 1}, headers=headers
    )
    response = await client.post(
        "/cart/items", json={"product_id": str(product.id), "variant_id": v2["id"], "quantity": 1}, headers=headers
    )

    assert len(response.json()["vendors"][0]["items"]) == 2


async def test_add_item_without_variant_id_on_product_with_variants_is_rejected(
    client: AsyncClient, db_session: AsyncSession, vendor_user: User, buyer_user: User, product: Product
) -> None:
    await client.post(
        f"/products/{product.id}/variants",
        json={"attributes": [{"name": "Taille", "value": "S"}], "stock": 5},
        headers=auth_headers(vendor_user),
    )
    await db_session.refresh(product, attribute_names=["variants"])  # voir le commentaire équivalent plus haut

    response = await client.post(
        "/cart/items", json={"product_id": str(product.id), "quantity": 1}, headers=auth_headers(buyer_user)
    )

    assert response.status_code == 409


async def test_add_item_with_variant_id_on_product_without_variants_is_rejected(
    client: AsyncClient, buyer_user: User, product: Product
) -> None:
    response = await client.post(
        "/cart/items",
        json={"product_id": str(product.id), "variant_id": str(uuid.uuid4()), "quantity": 1},
        headers=auth_headers(buyer_user),
    )

    assert response.status_code == 409


async def test_cart_exposes_a_generic_delivery_estimate_per_vendor(
    client: AsyncClient, db_session: AsyncSession, buyer_user: User, vendor: Vendor, product: Product
) -> None:
    vendor.preparation_days = 3
    await db_session.flush()

    response = await client.post(
        "/cart/items", json={"product_id": str(product.id), "quantity": 1}, headers=auth_headers(buyer_user)
    )

    today = date.today()
    group = response.json()["vendors"][0]
    # Destination inconnue au stade du panier et aucun palier configuré ici :
    # repli par défaut à 1 jour de trajet (voir app/cart/service.py::get_cart
    # et app/delivery/service.py::compute_transit_days).
    assert group["estimated_delivery_min"] == str(today + timedelta(days=4))
    assert group["estimated_delivery_max"] == str(today + timedelta(days=5))
