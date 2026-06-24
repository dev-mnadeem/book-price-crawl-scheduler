from __future__ import annotations

import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import DBDep, rate_limit_dep
from app.models.book import BookPublic, PaginatedBooks
from app.utils.text import normalize_category

router = APIRouter(
    prefix="/books",
    tags=["books"],
    dependencies=[Depends(rate_limit_dep)],
)


@router.get(
    "",
    response_model=PaginatedBooks,
    summary="List books",
    description="Browse the catalog filtered by category, price range and rating, with sorting and pagination.",
)
async def list_books(
    db: AsyncDatabase = DBDep,
    category: Optional[str] = Query(default=None, description="Filter by category name."),
    min_price: Optional[float] = Query(default=None, ge=0, description="Minimum price_incl_tax."),
    max_price: Optional[float] = Query(default=None, ge=0, description="Maximum price_incl_tax."),
    rating: Optional[int] = Query(default=None, ge=0, le=5, description="Exact star rating to match (0-5)."),
    sort_by: Literal["rating", "price", "reviews"] = Query(
        default="rating", description="Sort by rating, price, or reviews."
    ),
    order: Literal["asc", "desc"] = Query(default="desc", description="Sort order."),
    page: int = Query(default=1, ge=1, description="Page number (1-based)."),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page."),
):
    q: dict = {}
    if category:
        norm = normalize_category(category)
        # Prefer exact match on normalized field; include legacy case-insensitive category fallback
        q["$or"] = [
            {"category_norm": norm},
            {"category": {"$regex": f"^{re.escape(category)}$", "$options": "i"}},
        ]
    price_cond: dict = {}
    if min_price is not None:
        price_cond["$gte"] = float(min_price)
    if max_price is not None:
        price_cond["$lte"] = float(max_price)
    if price_cond:
        q["price_incl_tax"] = price_cond
    if rating is not None:
        q["rating"] = int(rating)

    field = {"rating": "rating", "price": "price_incl_tax", "reviews": "num_reviews"}[sort_by]
    direction = 1 if order == "asc" else -1

    total = await db["books"].count_documents(q)
    cursor = (
        db["books"]
        .find(q, projection={"_id": 0, "raw_html": 0, "content_hash": 0})
        # upc breaks ties so that books sharing a rating or price keep a fixed
        # order between pages instead of reshuffling across skip/limit calls.
        .sort([(field, direction), ("upc", 1)])
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    items = [BookPublic(**doc) async for doc in cursor]
    return PaginatedBooks(total=total, page=page, page_size=page_size, items=items)


@router.get(
    "/{book_id}",
    response_model=BookPublic,
    summary="Get book by UPC",
    description="Return the book by its UPC. Set include_raw=true to include raw_html and content_hash.",
)
async def get_book(
    book_id: str,
    db: AsyncDatabase = DBDep,
    include_raw: bool = Query(default=False, description="Include raw_html and content_hash in the response."),
):
    projection = {"_id": 0}
    if not include_raw:
        projection.update({"raw_html": 0, "content_hash": 0})
    doc = await db["books"].find_one({"upc": book_id}, projection=projection)
    if not doc:
        raise HTTPException(status_code=404, detail="Book not found")
    if include_raw:
        return JSONResponse(content=jsonable_encoder(doc))
    return BookPublic(**doc)
