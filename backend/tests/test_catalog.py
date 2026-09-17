"""Tests for category/product CRUD, pagination and filters."""

from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Category, Product
from app.users.models import User, UserRole
from app.vendors.models import Vendor, VendorStatus
from tests.conftest import auth_headers, make_user


async def test_create_and_list_categories(client: AsyncClient, admin_user: User) -> None:
    create_response = await client.post("/categories", json={"name": "Mode"}, headers=auth_headers(admin_user))
    assert create_response.status_code == 201

    list_response = await client.get("/categories")
    assert list_response.status_code == 200
    assert any(c["name"] == "Mode" for c in list_response.json())


async def test_create_product_requires_vendor_role(
    client: AsyncClient, buyer_user: User, category: Category
) -> None:
    response = await client.post(
        "/products",
        json={"category_id": str(category.id), "name": "Téléphone", "price": 500000, "stock": 10},
        headers=auth_headers(buyer_user),
    )

    assert response.status_code == 403


async def test_create_product_requires_approved_vendor(
    client: AsyncClient, unapproved_vendor_user: User, category: Category
) -> None:
    response = await client.post(
        "/products",
        json={"category_id": str(category.id), "name": "Téléphone", "price": 500000, "stock": 10},
        headers=auth_headers(unapproved_vendor_user),
    )

    assert response.status_code == 403
    assert "validée" in response.json()["detail"]


async def test_vendor_can_create_and_read_product(
    client: AsyncClient, vendor_user: User, category: Category
) -> None:
    response = await client.post(
        "/products",
        json={"category_id": str(category.id), "name": "Téléphone", "price": 500000, "stock": 10},
        headers=auth_headers(vendor_user),
    )

    assert response.status_code == 201
    product = response.json()
    assert product["price"] == 500000
    assert product["status"] == "active"

    get_response = await client.get(f"/products/{product['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Téléphone"


async def test_product_filters_price_and_stock(
    client: AsyncClient, vendor_user: User, category: Category
) -> None:
    headers = auth_headers(vendor_user)
    await client.post(
        "/products",
        json={"category_id": str(category.id), "name": "Casque", "price": 100000, "stock": 0},
        headers=headers,
    )
    await client.post(
        "/products",
        json={"category_id": str(category.id), "name": "Ordinateur", "price": 2000000, "stock": 5},
        headers=headers,
    )

    response = await client.get("/products", params={"min_price": 500000, "in_stock": True})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Ordinateur"


async def test_product_pagination(client: AsyncClient, vendor_user: User, category: Category) -> None:
    headers = auth_headers(vendor_user)
    for i in range(3):
        await client.post(
            "/products",
            json={"category_id": str(category.id), "name": f"Produit {i}", "price": 1000, "stock": 1},
            headers=headers,
        )

    response = await client.get("/products", params={"page": 1, "page_size": 2})

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    assert body["total"] == 3
    assert body["pages"] == 2


async def test_vendor_cannot_update_another_vendors_product(
    client: AsyncClient, db_session: AsyncSession, vendor_user: User, category: Category
) -> None:
    other_user = await make_user(db_session, phone="+224620009999", role=UserRole.VENDOR)
    other_vendor = Vendor(user_id=other_user.id, shop_name="Autre Boutique", status=VendorStatus.APPROVED)
    db_session.add(other_vendor)
    await db_session.flush()

    create_response = await client.post(
        "/products",
        json={"category_id": str(category.id), "name": "Produit", "price": 1000, "stock": 1},
        headers=auth_headers(vendor_user),
    )
    product_id = create_response.json()["id"]

    response = await client.patch(
        f"/products/{product_id}", json={"price": 2000}, headers=auth_headers(other_user)
    )

    assert response.status_code == 403


async def test_product_sort_by_price(client: AsyncClient, vendor_user: User, category: Category) -> None:
    headers = auth_headers(vendor_user)
    await client.post(
        "/products",
        json={"category_id": str(category.id), "name": "Cher", "price": 900000, "stock": 1},
        headers=headers,
    )
    await client.post(
        "/products",
        json={"category_id": str(category.id), "name": "Pas cher", "price": 10000, "stock": 1},
        headers=headers,
    )

    response = await client.get("/products", params={"sort": "price_asc"})

    assert response.status_code == 200
    names = [item["name"] for item in response.json()["items"]]
    assert names == ["Pas cher", "Cher"]


async def test_my_products_filters_by_category_status_and_stock_level(
    client: AsyncClient, vendor_user: User, category: Category, db_session: AsyncSession
) -> None:
    headers = auth_headers(vendor_user)
    other_category = Category(name="Autre")
    db_session.add(other_category)
    await db_session.flush()

    await client.post(
        "/products",
        json={"category_id": str(category.id), "name": "Rupture", "price": 1000, "stock": 0},
        headers=headers,
    )
    faible = await client.post(
        "/products",
        json={"category_id": str(category.id), "name": "Faible", "price": 1000, "stock": 2},
        headers=headers,
    )
    await client.post(
        "/products",
        json={"category_id": str(other_category.id), "name": "Autre categorie", "price": 1000, "stock": 20},
        headers=headers,
    )
    inactive_id = faible.json()["id"]
    await client.patch(f"/products/{inactive_id}", json={"status": "inactive"}, headers=headers)

    by_category = await client.get("/products/me", params={"category_id": str(category.id)}, headers=headers)
    assert {p["name"] for p in by_category.json()["items"]} == {"Rupture", "Faible"}

    out_of_stock = await client.get("/products/me", params={"stock_level": "out"}, headers=headers)
    assert [p["name"] for p in out_of_stock.json()["items"]] == ["Rupture"]

    inactive_only = await client.get("/products/me", params={"status": "inactive"}, headers=headers)
    assert [p["name"] for p in inactive_only.json()["items"]] == ["Faible"]


async def test_product_read_exposes_generic_delivery_estimate(
    client: AsyncClient, db_session: AsyncSession, vendor_user: User, vendor: Vendor, category: Category
) -> None:
    vendor.preparation_days = 3
    await db_session.flush()

    create_response = await client.post(
        "/products",
        json={"category_id": str(category.id), "name": "Produit", "price": 1000, "stock": 1},
        headers=auth_headers(vendor_user),
    )
    product_id = create_response.json()["id"]

    response = await client.get(f"/products/{product_id}")

    today = date.today()
    body = response.json()
    # Zone acheteur inconnue sur le catalogue public : hypothèse "zone
    # différente" par défaut (voir app/catalog/service.py::_attach_delivery_estimate).
    assert body["estimated_delivery_min"] == str(today + timedelta(days=4))
    assert body["estimated_delivery_max"] == str(today + timedelta(days=5))


async def test_admin_can_delete_any_product(
    client: AsyncClient, vendor_user: User, admin_user: User, category: Category
) -> None:
    create_response = await client.post(
        "/products",
        json={"category_id": str(category.id), "name": "Produit", "price": 1000, "stock": 1},
        headers=auth_headers(vendor_user),
    )
    product_id = create_response.json()["id"]

    response = await client.delete(f"/products/{product_id}", headers=auth_headers(admin_user))

    assert response.status_code == 200
    assert (await client.get(f"/products/{product_id}")).status_code == 404


# --- Product variants ---


async def test_vendor_can_create_variant_with_generic_attributes(
    client: AsyncClient, db_session: AsyncSession, vendor_user: User, product: Product
) -> None:
    response = await client.post(
        f"/products/{product.id}/variants",
        json={"attributes": [{"name": "Couleur", "value": "Rouge"}, {"name": "Taille", "value": "M"}], "stock": 3},
        headers=auth_headers(vendor_user),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["stock"] == 3
    assert {(a["name"], a["value"]) for a in body["attributes"]} == {("Couleur", "Rouge"), ("Taille", "M")}

    # La collection Product.variants a été chargée (vide) par ce même appel
    # POST plus haut, dans la même session de test partagée entre requêtes —
    # sans ce rafraîchissement ciblé, elle resterait figée à vide pour le
    # reste du test (une vraie requête HTTP séparée en production n'a pas ce
    # souci, chaque requête ouvrant sa propre session). expire_all() serait
    # trop large ici : ça périmerait aussi vendor_user etc., dont l'accès
    # synchrone ensuite (hors contexte async) ferait planter SQLAlchemy.
    await db_session.refresh(product, attribute_names=["variants"])

    get_response = await client.get(f"/products/{product.id}")
    assert len(get_response.json()["variants"]) == 1


async def test_create_variant_requires_at_least_one_attribute(
    client: AsyncClient, vendor_user: User, product: Product
) -> None:
    response = await client.post(
        f"/products/{product.id}/variants",
        json={"attributes": [], "stock": 3},
        headers=auth_headers(vendor_user),
    )

    assert response.status_code == 422


async def test_vendor_cannot_create_variant_for_another_vendors_product(
    client: AsyncClient, db_session: AsyncSession, product: Product
) -> None:
    other_user = await make_user(db_session, phone="+224620009998", role=UserRole.VENDOR)
    other_vendor = Vendor(user_id=other_user.id, shop_name="Autre Boutique 2", status=VendorStatus.APPROVED)
    db_session.add(other_vendor)
    await db_session.flush()

    response = await client.post(
        f"/products/{product.id}/variants",
        json={"attributes": [{"name": "Couleur", "value": "Bleu"}]},
        headers=auth_headers(other_user),
    )

    assert response.status_code == 403


async def test_creating_variants_updates_product_stock_denormalized_total(
    client: AsyncClient, vendor_user: User, product: Product
) -> None:
    headers = auth_headers(vendor_user)
    await client.post(
        f"/products/{product.id}/variants",
        json={"attributes": [{"name": "Taille", "value": "S"}], "stock": 3},
        headers=headers,
    )
    await client.post(
        f"/products/{product.id}/variants",
        json={"attributes": [{"name": "Taille", "value": "M"}], "stock": 5},
        headers=headers,
    )

    response = await client.get(f"/products/{product.id}")

    assert response.json()["stock"] == 8


async def test_update_variant_stock_adjusts_product_stock(
    client: AsyncClient, vendor_user: User, product: Product
) -> None:
    headers = auth_headers(vendor_user)
    created = await client.post(
        f"/products/{product.id}/variants",
        json={"attributes": [{"name": "Taille", "value": "S"}], "stock": 3},
        headers=headers,
    )
    variant_id = created.json()["id"]

    await client.patch(f"/products/{product.id}/variants/{variant_id}", json={"stock": 9}, headers=headers)
    response = await client.get(f"/products/{product.id}")

    assert response.json()["stock"] == 9


async def test_delete_variant_recomputes_product_stock(
    client: AsyncClient, vendor_user: User, product: Product
) -> None:
    headers = auth_headers(vendor_user)
    first = await client.post(
        f"/products/{product.id}/variants",
        json={"attributes": [{"name": "Taille", "value": "S"}], "stock": 3},
        headers=headers,
    )
    await client.post(
        f"/products/{product.id}/variants",
        json={"attributes": [{"name": "Taille", "value": "M"}], "stock": 5},
        headers=headers,
    )

    await client.delete(f"/products/{product.id}/variants/{first.json()['id']}", headers=headers)
    response = await client.get(f"/products/{product.id}")

    assert response.json()["stock"] == 5


async def test_updating_product_stock_directly_is_rejected_once_variants_exist(
    client: AsyncClient, db_session: AsyncSession, vendor_user: User, product: Product
) -> None:
    headers = auth_headers(vendor_user)
    await client.post(
        f"/products/{product.id}/variants",
        json={"attributes": [{"name": "Taille", "value": "S"}], "stock": 3},
        headers=headers,
    )
    await db_session.refresh(product, attribute_names=["variants"])  # voir le commentaire équivalent plus haut

    response = await client.patch(f"/products/{product.id}", json={"stock": 999}, headers=headers)

    assert response.status_code == 409


# --- Description : assainissement du mini éditeur riche ---


async def test_product_description_strips_disallowed_tags_and_attributes(
    client: AsyncClient, vendor_user: User, category: Category
) -> None:
    dirty = (
        '<p>Bonjour <strong>le monde</strong></p><script>alert(1)</script>'
        '<img src=x onerror=alert(2)><a href="javascript:alert(3)">clic</a><ul><li>un</li></ul>'
    )
    response = await client.post(
        "/products",
        json={"category_id": str(category.id), "name": "Produit", "price": 1000, "stock": 1, "description": dirty},
        headers=auth_headers(vendor_user),
    )

    assert response.status_code == 201
    assert response.json()["description"] == "<p>Bonjour <strong>le monde</strong></p>clic<ul><li>un</li></ul>"


async def test_updating_product_description_is_also_sanitized(
    client: AsyncClient, vendor_user: User, product: Product
) -> None:
    response = await client.patch(
        f"/products/{product.id}",
        json={"description": "<p onclick=\"alert(1)\">Texte <em>en italique</em></p>"},
        headers=auth_headers(vendor_user),
    )

    assert response.status_code == 200
    assert response.json()["description"] == "<p>Texte <em>en italique</em></p>"
