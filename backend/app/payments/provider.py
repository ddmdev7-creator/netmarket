"""Abstract payment provider interface.

CashOnDeliveryProvider: cash changes hands at delivery time, off-platform,
so "initiating" it is pure bookkeeping (see service.mark_paid, called once
every sub-order of an order is delivered — gated to this method only, see
app/orders/service.py::update_sub_order_status).

DjomyProvider: online payment (mobile money, cards...) via Djomy
(app/payments/djomy_client.py). Unlike cash, the money can be captured
before delivery — status changes come from the webhook
(app/payments/router.py), never from the delivery-completion path.
"""

from abc import ABC, abstractmethod

from app.core.config import get_settings
from app.orders.models import Order, PaymentMethod
from app.payments import djomy_client
from app.payments.models import PaymentStatus

settings = get_settings()


class PaymentProvider(ABC):
    @abstractmethod
    async def initiate(self, order: Order, *, payer_phone: str) -> tuple[PaymentStatus, str | None, str | None]:
        """Start payment for an order. `payer_phone` is the buyer's account
        phone by default, overridable at checkout (see CheckoutRequest.payer_phone)
        since the mobile money account paying isn't necessarily the buyer's own.
        Returns (initial status, provider reference, redirect url) — the
        redirect url is only set for a provider that sends the buyer to a
        hosted payment page; it is never persisted, only surfaced once on
        the checkout response (see app/orders/schemas.py::OrderRead)."""


class CashOnDeliveryProvider(PaymentProvider):
    async def initiate(self, order: Order, *, payer_phone: str) -> tuple[PaymentStatus, str | None, str | None]:
        return PaymentStatus.PENDING, None, None


class DjomyProvider(PaymentProvider):
    async def initiate(self, order: Order, *, payer_phone: str) -> tuple[PaymentStatus, str | None, str | None]:
        return_url = f"{settings.frontend_url}/commandes/{order.id}?djomy=return"
        transaction_id, redirect_url = await djomy_client.initiate_gateway_payment(
            amount=order.total,
            payer_number=payer_phone,
            reference=str(order.id),
            description=f"Commande netmarket #{str(order.id)[:8].upper()}",
            return_url=return_url,
        )
        return PaymentStatus.PENDING, transaction_id, redirect_url


_PROVIDERS: dict[PaymentMethod, PaymentProvider] = {
    PaymentMethod.CASH_ON_DELIVERY: CashOnDeliveryProvider(),
    PaymentMethod.ONLINE: DjomyProvider(),
}


def get_provider(method: PaymentMethod) -> PaymentProvider:
    return _PROVIDERS[method]
