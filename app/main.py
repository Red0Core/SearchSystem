"""FastAPI application wiring the search service."""
from __future__ import annotations

import logging
from fastapi import FastAPI, HTTPException, Query

from .brands import init_brands
from .config import settings
from .es_client import create_index_if_not_exists, get_client, index_is_empty
from .etl_loader import load_offers_to_es
from .models import ProductResult, SearchResponse
from .search_service import search_products
from .utils import QueryKind

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Product Search Service")


@app.on_event("startup")
async def startup_event() -> None:
    init_brands()
    create_index_if_not_exists()
    if settings.load_on_startup and index_is_empty():
        try:
            count = load_offers_to_es()
            logger.info("Loaded %s offers into Elasticsearch", count)
        except FileNotFoundError as exc:
            logger.warning("Offers file missing: %s", exc)


@app.get("/health")
async def health() -> dict:
    client = get_client()
    es_health = client.cluster.health()
    return {
        "elasticsearch": es_health.get("status"),
        "index": settings.es_index,
    }


@app.get("/search", response_model=SearchResponse)
async def search(q: str = Query(..., description="Search query")) -> SearchResponse:
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty")
    payload = search_products(q)
    products = [ProductResult(**item) for item in payload["results"]]
    return SearchResponse(
        query=payload["query"],
        classification=payload.get("classification", QueryKind.UNKNOWN),
        results=products,
        took_ms=payload["took_ms"],
        eta_ms=payload.get("eta_ms", payload["took_ms"]),
    )


@app.post("/reindex")
async def reindex() -> dict:
    count = load_offers_to_es()
    return {"indexed": count}
