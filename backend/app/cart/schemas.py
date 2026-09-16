"""Cart schemas. The cart is returned grouped by vendor, since checkout splits
it into one sub-order per vendor."""

import uuid

from pydantic import BaseModel, Field


class CartItemCreate(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(default=1, ge=1)


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=1)


class CartItemRead(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
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


class CartRead(BaseModel):
    vendors: list[VendorCartGroup]
    total: int
