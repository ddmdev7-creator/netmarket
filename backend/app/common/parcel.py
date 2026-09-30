"""Taille de colis S / M / L / XL (décision métier 2026-09-30).

Le vendeur déclare une taille par produit ; au checkout, le colis d'une
boutique prend la taille de son plus gros article, et une taille de plus
au-delà de BULK_THRESHOLD articles. Le gestionnaire du point de retrait peut
la corriger à l'arrivée du colis (tracé : declared_parcel_size reste celle
calculée). La taille fixe la rémunération du point et, pour L/XL, un
supplément sur les frais de livraison (réglages dans PaymentSettings).
"""

from enum import StrEnum


class ParcelSize(StrEnum):
    S = "S"
    M = "M"
    L = "L"
    XL = "XL"


ORDER = [ParcelSize.S, ParcelSize.M, ParcelSize.L, ParcelSize.XL]
# Plus de 5 articles dans le colis : une taille au-dessus.
BULK_THRESHOLD = 5


def parcel_size_for(item_sizes: list[tuple[str | None, int]]) -> ParcelSize:
    """(taille déclarée du produit, quantité) pour chaque ligne du colis."""
    if not item_sizes:
        return ParcelSize.S
    biggest = max(ORDER.index(ParcelSize(size or ParcelSize.S)) for size, _ in item_sizes)
    if sum(quantity for _, quantity in item_sizes) > BULK_THRESHOLD:
        biggest = min(biggest + 1, len(ORDER) - 1)
    return ORDER[biggest]


def pickup_fee_for(settings_row, size: str | None) -> int:
    """Rémunération de base du point de retrait pour un colis remis."""
    return {
        ParcelSize.S: settings_row.pickup_point_fee_per_parcel,
        ParcelSize.M: settings_row.pickup_fee_m,
        ParcelSize.L: settings_row.pickup_fee_l,
        ParcelSize.XL: settings_row.pickup_fee_xl,
    }[ParcelSize(size or ParcelSize.S)]


def delivery_surcharge_for(settings_row, size: str | None) -> int:
    """Supplément acheteur sur la course pour un colis encombrant."""
    return {
        ParcelSize.L: settings_row.delivery_surcharge_l,
        ParcelSize.XL: settings_row.delivery_surcharge_xl,
    }.get(ParcelSize(size or ParcelSize.S), 0)
