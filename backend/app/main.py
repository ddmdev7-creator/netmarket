"""FastAPI application factory: mounts routers and registers error handlers."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.addresses.router import router as addresses_router
from app.admin.router import router as admin_router
from app.auth.router import router as auth_router
from app.cart.router import router as cart_router
from app.catalog.router import router as catalog_router
from app.core.exceptions import register_exception_handlers
from app.delivery.router import admin_router as delivery_admin_router
from app.couriers.router import admin_router as couriers_admin_router
from app.couriers.router import router as couriers_router
from app.notifications.router import router as notifications_router
from app.orders.router import router as orders_router
from app.payments.router import router as payments_router
from app.pickup_point_managers.router import admin_router as pickup_point_managers_admin_router
from app.pickup_point_managers.router import router as pickup_point_managers_router
from app.pickup_points.router import admin_router as pickup_points_admin_router
from app.pickup_points.router import router as pickup_points_router
from app.reports.router import admin_router as reports_admin_router
from app.reports.router import router as reports_router
from app.reviews.router import router as reviews_router
from app.subscriptions.router import admin_router as subscriptions_admin_router
from app.subscriptions.router import router as subscriptions_router
from app.uploads.router import router as uploads_router
from app.users.router import admin_router as users_admin_router
from app.users.router import router as users_router
from app.vendors.router import admin_router as vendors_admin_router
from app.vendors.router import router as vendors_router

app = FastAPI(title="Marketplace Guinée API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(auth_router)
app.include_router(addresses_router)
app.include_router(users_router)
app.include_router(users_admin_router)
app.include_router(catalog_router)
app.include_router(vendors_router)
app.include_router(vendors_admin_router)
app.include_router(couriers_router)
app.include_router(couriers_admin_router)
app.include_router(delivery_admin_router)
app.include_router(cart_router)
app.include_router(orders_router)
app.include_router(payments_router)
app.include_router(pickup_points_router)
app.include_router(pickup_points_admin_router)
app.include_router(pickup_point_managers_router)
app.include_router(pickup_point_managers_admin_router)
app.include_router(reviews_router)
app.include_router(reports_router)
app.include_router(reports_admin_router)
app.include_router(uploads_router)
app.include_router(subscriptions_router)
app.include_router(subscriptions_admin_router)
app.include_router(admin_router)
app.include_router(notifications_router)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
