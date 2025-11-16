"""Pydantic models for request/response payloads."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .utils import QueryKind


class SearchRequest(BaseModel):
    q: str = Field(..., description="Search query string")


class ProductResult(BaseModel):
    id: str
    manufacturer: str | None = None
    product_code: str | None = None
    title: str | None = None
    score: float | None = None


class SearchResponse(BaseModel):
    query: str
    classification: QueryKind
    results: list[ProductResult]
    took_ms: float
    eta_ms: float
