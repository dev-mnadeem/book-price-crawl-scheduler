from __future__ import annotations

import asyncio
import logging

from fastapi import Depends, FastAPI
from fastapi.responses import ORJSONResponse

from app.api.deps import APIKeyDep
from app.api.routers import books, changes
from app.config.logging import setup_logging
from app.config.settings import settings
from app.db.indexes import ensure_indexes
from app.db.mongo import close_client, get_db
from app.scheduler.main import start_scheduler_embedded, stop_scheduler_embedded

logger = logging.getLogger(__name__)

openapi_tags = [
    {"name": "books", "description": "Browse and query the books catalog with filtering, sorting, and pagination."},
    {"name": "changes", "description": "Inspect recent crawl changes such as new books and updates."},
]

app = FastAPI(
    title="Books Monitor API",
    version="1.0.0",
    description="API to browse a scraped catalog of books, view change logs, and query details.",
    openapi_tags=openapi_tags,
    default_response_class=ORJSONResponse,
)


@app.on_event("startup")
async def on_startup() -> None:
    setup_logging(settings.log_level)
    db = await get_db()
    await ensure_indexes(db)
    if settings.run_scheduler_in_api:
        await start_scheduler_embedded()
    logger.info("API startup complete")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    if settings.run_scheduler_in_api:
        await stop_scheduler_embedded()
    await close_client()
    logger.info("API shutdown complete")


app.include_router(books.router)
app.include_router(changes.router)


@app.get("/health")
async def health(_: APIKeyDep) -> dict:
    return {"status": "ok"}
