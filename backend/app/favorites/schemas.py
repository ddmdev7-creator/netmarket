import uuid
from datetime import datetime

from pydantic import BaseModel

from app.catalog.schemas import ProductRead


class FavoriteRead(BaseModel):
    product: ProductRead
    price_at_add: int
    created_at: datetime


class FavoriteIds(BaseModel):
    product_ids: list[uuid.UUID]
