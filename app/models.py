"""Pydantic models for request/response payloads."""
from __future__ import annotations

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    q: str = Field(..., description="Search query string")


class ProductResult(BaseModel):
    externalId: str | None = None
    manufacturer: str | None = None
    productCode: str | None = None
    title: str | None = None
    phonetic: str | None = None
    price: float | None = None
    category: str | None = None
    currency: str | None = None
    score: float | None = None


class SearchResponse(BaseModel):
    query: str
    classification: str
    results: list[ProductResult]
    took_ms: float
    eta_ms: float
