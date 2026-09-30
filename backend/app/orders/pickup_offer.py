"""« Retrait offert » : le vendeur prend en charge la livraison vers un point
de retrait.

Règles (décidées avec le métier) :
- uniquement pour une livraison en point de retrait ;
- à partir du montant minimum d'achat réglé par le vendeur dans sa boutique ;
- jusqu'à sa distance maximale boutique → point, s'il en a fixé une (au-delà,
  ou si la distance est inconnue, l'offre ne s'applique pas) ;
- dans la limite de son plafond de prise en charge, s'il en a fixé un :
  l'acheteur paie alors le reste de la course (offre partielle) ;
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
    # Plafond de prise en charge atteint : le vendeur paie une partie.
    PARTIAL = "partial"
    BELOW_MINIMUM = "below_minimum"
    OUT_OF_RANGE = "out_of_range"
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
    db: AsyncSession,
    vendor: Vendor,
    *,
    amount: int,
    fee: int,
    is_pickup: bool,
    distance_km: float | None = None,
    reserved: int = 0,
) -> DeliverySplit:
    """Qui paie la course de ce colis. `distance_km` : boutique → point de
    retrait (None si inconnue). `reserved` : retraits offerts déjà accordés
    par ce même vendeur plus haut dans le même calcul."""
    if not is_pickup or not vendor.offers_pickup_delivery or fee <= 0:
        return DeliverySplit(buyer_fee=fee, vendor_fee=0, offer=None)
    if amount < vendor.pickup_offer_min_amount:
        return DeliverySplit(
            buyer_fee=fee,
            vendor_fee=0,
            offer=OfferStatus.BELOW_MINIMUM,
            missing_amount=vendor.pickup_offer_min_amount - amount,
        )
    max_km = vendor.pickup_offer_max_km
    if max_km is not None and (distance_km is None or distance_km > max_km):
        return DeliverySplit(buyer_fee=fee, vendor_fee=0, offer=OfferStatus.OUT_OF_RANGE)
    cap = vendor.pickup_offer_max_amount
    covered = fee if cap is None else min(fee, cap)
    if covered <= 0 or await offer_capacity(db, vendor) - reserved < covered:
        return DeliverySplit(buyer_fee=fee, vendor_fee=0, offer=OfferStatus.UNAVAILABLE)
    return DeliverySplit(
        buyer_fee=fee - covered,
        vendor_fee=covered,
        offer=OfferStatus.APPLIED if covered == fee else OfferStatus.PARTIAL,
    )
