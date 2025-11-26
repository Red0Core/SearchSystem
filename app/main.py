"""FastAPI application wiring the search service."""
from __future__ import annotations

import asyncio
import logging
from typing import List

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .es_client import get_client
from .importer import import_if_empty, reindex_data
from .indexing import ensure_index, index_is_empty
from .models import ProductResult, SearchResponse
from .search import search_products

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.getLevelName(settings.log_level.upper()))

app = FastAPI(title="Product Search Service")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
async def startup_event() -> None:
    es = get_client()
    await ensure_index(es)
    if settings.load_on_startup:
        imported = await import_if_empty(es)
        if imported:
            logger.info("Imported %s products on startup", imported)


@app.get("/health")
async def health() -> dict:
    es = get_client()
    status = await asyncio.to_thread(es.cluster.health)
    empty = await index_is_empty(es)
    return {
        "elasticsearch": status.get("status"),
        "index": settings.es_index,
        "empty": empty,
    }


@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    return FileResponse("static/index.html")


@app.get("/search", response_model=SearchResponse)
async def search(q: str = Query(..., description="Search query"), limit: int = 50) -> SearchResponse:
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty")
    es = get_client()
    payload = await search_products(es, settings.es_index, q, limit)
    products: List[ProductResult] = [ProductResult(**item) for item in payload["results"]]
    return SearchResponse(query=payload["query"], classification="unknown", results=products, took_ms=payload["took_ms"], eta_ms=payload["took_ms"])


@app.post("/reindex")
async def reindex() -> dict:
    es = get_client()
    count = await reindex_data(es)
    return {"indexed": count}
