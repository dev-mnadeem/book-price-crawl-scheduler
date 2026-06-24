from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class BookPublic(BaseModel):
    upc: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    category_norm: Optional[str] = None
    price_excl_tax: Optional[float] = None
    price_incl_tax: Optional[float] = None
    availability: Optional[int] = 0
    num_reviews: Optional[int] = 0
    image_url: Optional[str] = None
    rating: Optional[int] = None
    source_url: str
    in_stock: Optional[bool] = None
    currency: Optional[str] = None


class PaginatedBooks(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[BookPublic]
