"""Cart schemas. The cart is returned grouped by vendor, since checkout splits
it into one sub-order per vendor."""

import uuid
from datetime import date

from pydantic import BaseModel, Field


class CartItemCreate(BaseModel):
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    quantity: int = Field(default=1, ge=1)


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=1)


class CartItemRead(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    variant_label: str | None = None
    product_name: str
    product_image: str | None = None
    unit_price: int
    quantity: int
    subtotal: int


class VendorCartGroup(BaseModel):
    vendor_id: uuid.UUID
    shop_name: str
    items: list[CartItemRead]
    subtotal: int
    # Estimation générique (même principe que ProductRead sur le catalogue,
    # voir app/catalog/service.py::_attach_delivery_estimate) : l'adresse de
    # livraison n'est pas encore connue au stade du panier, donc calculée
    # sans position réelle — retombe sur le palier de repli de la grille de
    # distance. Recalculée (et éventuellement affinée avec la vraie
    # distance) au devis de livraison puis figée au checkout.
    estimated_delivery_min: date | None = None
    estimated_delivery_max: date | None = None


class CartRead(BaseModel):
    vendors: list[VendorCartGroup]
    total: int
