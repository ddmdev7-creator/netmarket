"""Tests for product/review reporting and admin moderation (dismiss/action)."""

from httpx import AsyncClient

from app.catalog.models import Product
from app.couriers.models import Courier
from app.users.models import User, UserRole
from tests.conftest import auth_headers, make_user, scan_handoff

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
    delivered_step = await scan_handoff(client, courier_user, sub_order_id)
    assert delivered_step.status_code == 200


async def _leave_review(
    client: AsyncClient, buyer: User, vendor_user: User, product: Product, courier: Courier, courier_user: User
) -> str:
    await _buy_and_deliver(client, buyer, vendor_user, product, courier, courier_user)
    response = await client.post(
        f"/products/{product.id}/reviews", json={"rating": 2, "comment": "Pas terrible"}, headers=auth_headers(buyer)
    )
    assert response.status_code == 201
    return response.json()["id"]


# --- Signalement (côté acheteur) ---


async def test_report_product_success(client: AsyncClient, buyer_user: User, product: Product) -> None:
    response = await client.post(
        f"/products/{product.id}/reports", json={"reason": "Photo trompeuse"}, headers=auth_headers(buyer_user)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["report_type"] == "product"
    assert body["status"] == "pending"
    assert body["product_name"] == product.name


async def test_report_product_not_found(client: AsyncClient, buyer_user: User) -> None:
    response = await client.post(
        "/products/00000000-0000-0000-0000-000000000000/reports",
        json={"reason": "Produit inexistant"},
        headers=auth_headers(buyer_user),
    )

    assert response.status_code == 404


async def test_report_product_duplicate_is_rejected(client: AsyncClient, buyer_user: User, product: Product) -> None:
    headers = auth_headers(buyer_user)
    await client.post(f"/products/{product.id}/reports", json={"reason": "Motif 1"}, headers=headers)

    response = await client.post(f"/products/{product.id}/reports", json={"reason": "Motif 2"}, headers=headers)

    assert response.status_code == 409


async def test_report_review_success(
    client: AsyncClient, db_session, buyer_user: User, vendor_user: User, product: Product, courier: Courier, courier_user: User
) -> None:
    review_id = await _leave_review(client, buyer_user, vendor_user, product, courier, courier_user)
    other_buyer = await make_user(db_session, phone="+224620008881", role=UserRole.BUYER)

    response = await client.post(
        f"/reviews/{review_id}/reports", json={"reason": "Langage inapproprié"}, headers=auth_headers(other_buyer)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["report_type"] == "review"
    assert body["review_comment"] == "Pas terrible"
    assert body["review_rating"] == 2


async def test_report_review_duplicate_is_rejected(
    client: AsyncClient, buyer_user: User, vendor_user: User, product: Product, courier: Courier, courier_user: User
) -> None:
    review_id = await _leave_review(client, buyer_user, vendor_user, product, courier, courier_user)
    headers = auth_headers(buyer_user)
    await client.post(f"/reviews/{review_id}/reports", json={"reason": "Motif 1"}, headers=headers)

    response = await client.post(f"/reviews/{review_id}/reports", json={"reason": "Motif 2"}, headers=headers)

    assert response.status_code == 409


# --- Modération (côté admin) ---


async def test_non_admin_cannot_list_reports(client: AsyncClient, buyer_user: User) -> None:
    response = await client.get("/admin/reports", headers=auth_headers(buyer_user))

    assert response.status_code == 403


async def test_admin_list_reports_filtered(
    client: AsyncClient, admin_user: User, buyer_user: User, vendor_user: User, product: Product, courier: Courier, courier_user: User
) -> None:
    review_id = await _leave_review(client, buyer_user, vendor_user, product, courier, courier_user)
    await client.post(f"/products/{product.id}/reports", json={"reason": "Motif produit"}, headers=auth_headers(buyer_user))
    await client.post(f"/reviews/{review_id}/reports", json={"reason": "Motif avis"}, headers=auth_headers(vendor_user))

    admin_headers = auth_headers(admin_user)
    products_only = await client.get("/admin/reports", params={"type": "product"}, headers=admin_headers)
    assert len(products_only.json()) == 1
    assert products_only.json()[0]["report_type"] == "product"

    pending = await client.get("/admin/reports", params={"status": "pending"}, headers=admin_headers)
    assert len(pending.json()) == 2


async def test_admin_dismiss_report_has_no_side_effect(
    client: AsyncClient, admin_user: User, buyer_user: User, product: Product
) -> None:
    report = await client.post(
        f"/products/{product.id}/reports", json={"reason": "Motif"}, headers=auth_headers(buyer_user)
    )
    report_id = report.json()["id"]

    response = await client.patch(
        f"/admin/reports/{report_id}", json={"status": "dismissed"}, headers=auth_headers(admin_user)
    )

    assert response.status_code == 200
    assert response.json()["status"] == "dismissed"
    product_check = await client.get(f"/products/{product.id}")
    assert product_check.json()["status"] == "active"


async def test_admin_action_on_product_report_deactivates_product(
    client: AsyncClient, admin_user: User, buyer_user: User, product: Product
) -> None:
    report = await client.post(
        f"/products/{product.id}/reports", json={"reason": "Non conforme"}, headers=auth_headers(buyer_user)
    )
    report_id = report.json()["id"]

    response = await client.patch(
        f"/admin/reports/{report_id}",
        json={"status": "actioned", "admin_note": "Produit désactivé"},
        headers=auth_headers(admin_user),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "actioned"

    # Retiré du catalogue public...
    public_list = await client.get("/products")
    assert all(p["id"] != str(product.id) for p in public_list.json()["items"])
    # ...mais le statut du produit lui-même reflète bien la désactivation.
    product_check = await client.get(f"/products/{product.id}")
    assert product_check.json()["status"] == "inactive"


async def test_admin_action_on_review_report_deletes_review(
    client: AsyncClient, admin_user: User, buyer_user: User, vendor_user: User, product: Product, courier: Courier, courier_user: User
) -> None:
    review_id = await _leave_review(client, buyer_user, vendor_user, product, courier, courier_user)
    report = await client.post(
        f"/reviews/{review_id}/reports", json={"reason": "Contenu abusif"}, headers=auth_headers(vendor_user)
    )
    report_id = report.json()["id"]

    response = await client.patch(
        f"/admin/reports/{report_id}", json={"status": "actioned"}, headers=auth_headers(admin_user)
    )

    assert response.status_code == 200
    remaining = await client.get(f"/products/{product.id}/reviews")
    assert remaining.json() == []


async def test_admin_cannot_resolve_already_resolved_report(
    client: AsyncClient, admin_user: User, buyer_user: User, product: Product
) -> None:
    report = await client.post(
        f"/products/{product.id}/reports", json={"reason": "Motif"}, headers=auth_headers(buyer_user)
    )
    report_id = report.json()["id"]
    admin_headers = auth_headers(admin_user)
    await client.patch(f"/admin/reports/{report_id}", json={"status": "dismissed"}, headers=admin_headers)

    response = await client.patch(f"/admin/reports/{report_id}", json={"status": "actioned"}, headers=admin_headers)

    assert response.status_code == 409


# --- Régression : filtre du catalogue public sur les produits inactifs ---


async def test_public_catalog_excludes_inactive_products(
    client: AsyncClient, vendor_user: User, product: Product
) -> None:
    await client.patch(f"/products/{product.id}", json={"status": "inactive"}, headers=auth_headers(vendor_user))

    public_list = await client.get("/products")

    assert all(p["id"] != str(product.id) for p in public_list.json()["items"])


async def test_vendor_own_product_list_still_includes_inactive(
    client: AsyncClient, vendor_user: User, product: Product
) -> None:
    await client.patch(f"/products/{product.id}", json={"status": "inactive"}, headers=auth_headers(vendor_user))

    own_list = await client.get("/products/me", headers=auth_headers(vendor_user))

    assert any(p["id"] == str(product.id) for p in own_list.json()["items"])
