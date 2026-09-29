"""« Retrait offert » : le vendeur prend en charge la livraison vers un point
de retrait.

Règles (décidées avec le métier) :
- uniquement pour une livraison en point de retrait, quelle que soit la distance ;
- à partir du montant minimum d'achat réglé par le vendeur dans sa boutique ;
- seulement si son solde NdjouriBank disponible couvre la course, déduction
  faite des retraits offerts déjà engagés sur des colis en cours : pas de
  solde négatif. Sinon l'acheteur paie la livraison comme d'habitude ;
- la course est prélevée sur son solde à la livraison (voir
  app/wallets/service.py::settle_sub_order) ; rien n'est prélevé si le colis
  est annulé.
"""

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from app.vendors.models import Vendor
from app.wallets import service as wallets_service
from app.wallets.models import AccountKind


class OfferStatus(StrEnum):
    APPLIED = "applied"
    BELOW_MINIMUM = "below_minimum"
    UNAVAILABLE = "unavailable"


@dataclass
class DeliverySplit:
    buyer_fee: int
    vendor_fee: int
    offer: OfferStatus | None
    # Montant d'achat manquant pour débloquer l'offre (BELOW_MINIMUM).
    missing_amount: int = 0


async def offer_capacity(db: AsyncSession, vendor: Vendor) -> int:
    """Ce que le vendeur peut encore offrir : solde disponible moins les
    retraits offerts engagés sur des colis en cours."""
    balance = await wallets_service.get_wallet_balance(db, AccountKind.VENDOR, vendor.id)
    available = balance.available if balance is not None else 0
    return available - await wallets_service.committed_pickup_offers(db, vendor.id)


async def split_delivery_fee(
    db: AsyncSession, vendor: Vendor, *, amount: int, fee: int, is_pickup: bool, reserved: int = 0
) -> DeliverySplit:
    """Qui paie la course de ce colis. `reserved` : retraits offerts déjà
    accordés par ce même vendeur plus haut dans le même calcul."""
    if not is_pickup or not vendor.offers_pickup_delivery or fee <= 0:
        return DeliverySplit(buyer_fee=fee, vendor_fee=0, offer=None)
    if amount < vendor.pickup_offer_min_amount:
        return DeliverySplit(
            buyer_fee=fee,
            vendor_fee=0,
            offer=OfferStatus.BELOW_MINIMUM,
            missing_amount=vendor.pickup_offer_min_amount - amount,
        )
    if await offer_capacity(db, vendor) - reserved < fee:
        return DeliverySplit(buyer_fee=fee, vendor_fee=0, offer=OfferStatus.UNAVAILABLE)
    return DeliverySplit(buyer_fee=0, vendor_fee=fee, offer=OfferStatus.APPLIED)
