"""Pydantic schemas: categories, products, and product search filters."""

import uuid
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Literal

from fastapi import Query
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field

from app.catalog.models import ProductStatus


class ProductSort(StrEnum):
    RECENT = "recent"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    TOP_RATED = "top_rated"
    # Vendeur : produits les moins stockés d'abord (réapprovisionnement).
    STOCK_ASC = "stock_asc"
    # Boutiques les plus proches de near_lat/near_lng (repli sur "recent" sans position).
    NEAREST = "nearest"


StockLevel = Literal["out", "low"]


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    parent_id: uuid.UUID | None = None
    icon: str | None = Field(default=None, max_length=40)


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    # None remet la catégorie à la racine — d'où exclude_unset côté service
    # pour distinguer "non fourni" de "explicitement null".
    parent_id: uuid.UUID | None = None
    icon: str | None = Field(default=None, max_length=40)


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    icon: str | None = None


class ProductCreate(BaseModel):
    category_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    price: int = Field(ge=0, description="Prix en GNF, montant entier")
    stock: int = Field(default=0, ge=0)
    images: list[str] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    category_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    price: int | None = Field(default=None, ge=0)
    stock: int | None = Field(default=None, ge=0)
    images: list[str] | None = None
    status: ProductStatus | None = None


class ProductVariantAttributeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    value: str = Field(min_length=1, max_length=100)


class ProductVariantAttributeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    value: str


class ProductVariantCreate(BaseModel):
    sku: str | None = Field(default=None, max_length=64)
    price: int | None = Field(default=None, ge=0, description="Surcharge du prix produit — vide = même prix")
    stock: int = Field(default=0, ge=0)
    images: list[str] | None = None
    # Au moins 1 paire : une variante doit être distinguable (ex: Couleur=Rouge).
    attributes: list[ProductVariantAttributeCreate] = Field(min_length=1)


class ProductVariantUpdate(BaseModel):
    sku: str | None = None
    price: int | None = Field(default=None, ge=0)
    stock: int | None = Field(default=None, ge=0)
    images: list[str] | None = None
    # Fourni = remplace entièrement le jeu d'attributs existant (pas de diff
    # pair par pair, plus simple côté service — voir catalog/service.py).
    attributes: list[ProductVariantAttributeCreate] | None = Field(default=None, min_length=1)


class ProductVariantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    sku: str | None
    price: int | None
    stock: int
    images: list[str] | None
    attributes: list[ProductVariantAttributeRead]


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vendor_id: uuid.UUID
    vendor_shop_name: str
    category_id: uuid.UUID
    name: str
    description: str | None
    price: int
    stock: int
    images: list[str]
    status: ProductStatus
    average_rating: float | None = None
    review_count: int = 0
    # Estimation générique (zone acheteur inconnue à ce stade — voir
    # app/common/delivery_estimate.py) ; une estimation précise n'apparaît
    # qu'une fois la commande passée, une fois la zone de livraison connue.
    estimated_delivery_min: date | None = None
    estimated_delivery_max: date | None = None
    # Peuplé automatiquement via la relation SQLAlchemy Product.variants
    # (contrairement à average_rating/estimated_delivery_*, pas besoin du
    # pattern d'attribut transitoire — voir catalog/repository.py).
    variants: list[ProductVariantRead] = Field(default_factory=list)


@dataclass
class ProductFilters:
    category_id: uuid.UUID | None
    min_price: int | None
    max_price: int | None
    in_stock: bool | None
    q: str | None
    sort: ProductSort = ProductSort.RECENT
    near_lat: float | None = None
    near_lng: float | None = None
    ids: list[uuid.UUID] | None = None
    # Public (produits d'une boutique, suggestion "boutique" de la recherche) ;
    # forcé par catalog/service.py::list_my_products pour la liste du vendeur.
    vendor_id: uuid.UUID | None = None
    # Vendor-only filters (see my_product_filters below) — a vendor narrowing
    # their own "Mes produits" list, never exposed on the public catalog.
    status: ProductStatus | None = None
    stock_level: StockLevel | None = None


def product_filters(
    category_id: uuid.UUID | None = Query(default=None, description="Filtrer par catégorie"),
    min_price: int | None = Query(default=None, ge=0, description="Prix minimum en GNF"),
    max_price: int | None = Query(default=None, ge=0, description="Prix maximum en GNF"),
    in_stock: bool | None = Query(default=None, description="Uniquement les produits disponibles en stock"),
    q: str | None = Query(default=None, min_length=1, max_length=100, description="Recherche par nom de produit"),
    sort: ProductSort = Query(default=ProductSort.RECENT, description="Tri des résultats"),
    near_lat: float | None = Query(default=None, ge=-90, le=90, description="Latitude pour sort=nearest"),
    near_lng: float | None = Query(default=None, ge=-180, le=180, description="Longitude pour sort=nearest"),
    vendor_id: uuid.UUID | None = Query(default=None, description="Produits d'une boutique"),
    ids: str | None = Query(
        default=None, max_length=2000, description="Liste d'ids séparés par des virgules (vus récemment)"
    ),
) -> ProductFilters:
    id_list: list[uuid.UUID] | None = None
    if ids:
        try:
            id_list = [uuid.UUID(part) for part in ids.split(",") if part.strip()][:50]
        except ValueError as exc:
            raise RequestValidationError(
                [{"loc": ("query", "ids"), "msg": "Identifiant invalide.", "type": "value_error"}]
            ) from exc
    return ProductFilters(
        category_id=category_id,
        min_price=min_price,
        max_price=max_price,
        in_stock=in_stock,
        q=q,
        sort=sort,
        near_lat=near_lat,
        near_lng=near_lng,
        vendor_id=vendor_id,
        ids=id_list,
    )


def my_product_filters(
    category_id: uuid.UUID | None = Query(default=None, description="Filtrer par catégorie"),
    status: ProductStatus | None = Query(default=None, description="Filtrer par statut (actif/inactif)"),
    stock_level: StockLevel | None = Query(
        default=None, description="'out' = rupture de stock, 'low' = stock faible"
    ),
    sort: ProductSort = Query(default=ProductSort.RECENT, description="Tri des résultats"),
    q: str | None = Query(default=None, min_length=1, max_length=100, description="Recherche par nom"),
) -> ProductFilters:
    return ProductFilters(
        category_id=category_id,
        min_price=None,
        max_price=None,
        in_stock=None,
        q=q,
        sort=sort,
        status=status,
        stock_level=stock_level,
    )


class MyProductsSummary(BaseModel):
    """Compteurs de « Mes produits » (vendeur) et quantités vendues par produit."""

    total: int
    active: int
    inactive: int
    low_stock: int
    out_of_stock: int
    # Quantités vendues (commandes non annulées), par id produit.
    sold: dict[uuid.UUID, int]


class SuggestedProduct(BaseModel):
    id: uuid.UUID
    name: str
    price: int
    image: str | None


class SuggestedShop(BaseModel):
    id: uuid.UUID
    shop_name: str
    product_count: int


class SearchSuggestions(BaseModel):
    products: list[SuggestedProduct]
    categories: list[CategoryRead]
    shops: list[SuggestedShop]
    # Requête corrigée d'après les mots du catalogue, seulement quand la
    # recherche ne trouve rien ("ordinatuer" → "ordinateur").
    did_you_mean: str | None = None


class ProductDeliveryQuote(BaseModel):
    """Frais et délai de livraison de CE produit vers une position (fiche produit).
    Sans position, delivery_fee vaut None et seul le palier le moins cher
    (min_fee, "dès …") est connu."""

    delivery_fee: int | None
    min_fee: int
    distance_km: float | None
    estimated_delivery_min: date
    estimated_delivery_max: date
