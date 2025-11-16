"""Search logic built on top of Elasticsearch."""
from __future__ import annotations

import logging
from time import perf_counter
from typing import Dict, List

from .cache import get_cache
from .config import settings
from .es_client import search_es
from .utils import (
    QueryClassification,
    QueryKind,
    classify_query,
    hash_query,
    normalize_code,
    transliterate_query,
)

logger = logging.getLogger(__name__)
cache = get_cache()

SOURCE_FIELDS = ["id", "manufacturer", "product_code", "title"]


def _base_query(size: int) -> dict:
    return {
        "track_total_hits": False,
        "size": size,
        "_source": SOURCE_FIELDS,
        "query": {"bool": {"must": [], "should": [], "filter": []}},
    }


def build_es_query(raw_query: str, classification: QueryClassification) -> dict:
    query_text = (classification.get("query") or raw_query).strip() or raw_query
    transliterated = transliterate_query(query_text)
    kind = classification.get("kind", QueryKind.UNKNOWN)

    size = settings.search_result_size
    if kind in {QueryKind.BRAND_ONLY, QueryKind.BRAND_WITH_GENERIC}:
        size = min(size, settings.brand_result_size)

    base_query = _base_query(size)
    bool_clause = base_query["query"]["bool"]

    def add_should(clause: dict) -> None:
        bool_clause["should"].append(clause)

    def add_must(clause: dict) -> None:
        bool_clause["must"].append(clause)

    def add_filter(clause: dict) -> None:
        bool_clause["filter"].append(clause)

    def add_text_match(
        text: str,
        *,
        boost: float = 1.0,
        fields: List[str] | None = None,
        clause: str = "must",
    ) -> None:
        if not text:
            return
        clause_body = {
            "multi_match": {
                "query": text,
                "fields": fields
                or ["title^3", "search_text", "product_code", "manufacturer"],
                "fuzziness": "AUTO",
                "boost": boost,
            }
        }
        if clause == "should":
            add_should(clause_body)
        else:
            add_must(clause_body)

    def add_phonetic_should(text: str, *, boost: float = 1.0) -> None:
        if not text:
            return
        add_should(
            {
                "multi_match": {
                    "query": text,
                    "fields": ["manufacturer.phonetic^2", "title.phonetic"],
                    "type": "most_fields",
                    "boost": boost,
                }
            }
        )

    if kind == QueryKind.ARTICLE:
        normalized = classification.get("normalized_code") or normalize_code(query_text)
        if normalized:
            add_should({"term": {"product_code_normalized": {"value": normalized, "boost": 5}}})
        add_must(
            {
                "multi_match": {
                    "query": query_text,
                    "fields": ["product_code", "title", "search_text"],
                    "fuzziness": "AUTO",
                    "boost": 2.5,
                }
            }
        )
        return base_query

    if kind == QueryKind.URL:
        tokens: List[str] = classification.get("url_tokens", [])
        url_query = " ".join(tokens) if tokens else query_text
        add_must(
            {
                "multi_match": {
                    "query": url_query,
                    "fields": ["search_text", "search_text_tr", "title"],
                    "fuzziness": "AUTO",
                }
            }
        )
        return base_query

    brands: List[str] = classification.get("brands", [])
    brand_originals: Dict[str, str] = classification.get("brand_originals", {})
    generic_tokens: List[str] = classification.get("generic_tokens", [])
    generic_text = " ".join(generic_tokens).strip()
    brand_focus = " ".join(brand_originals.values()).strip() or query_text

    def apply_brand_filter() -> None:
        if brands:
            add_filter({"terms": {"manufacturer_normalized": brands}})

    def add_brand_should(boost: float = 2.0) -> None:
        if not brand_focus:
            return
        add_should(
            {
                "multi_match": {
                    "query": brand_focus,
                    "fields": ["manufacturer^3", "manufacturer.phonetic^2"],
                    "type": "most_fields",
                    "fuzziness": "AUTO",
                    "boost": boost,
                }
            }
        )

    if kind == QueryKind.BRAND_ONLY:
        apply_brand_filter()
        add_brand_should(boost=2.5)
        add_text_match(query_text, boost=0.8, fields=["title^2", "search_text"], clause="should")
    elif kind == QueryKind.BRAND_WITH_GENERIC:
        apply_brand_filter()
        if generic_text:
            add_text_match(generic_text, boost=1.2)
        else:
            add_text_match(query_text, boost=1.0)
        add_brand_should(boost=2.0)
    elif kind in (QueryKind.GENERIC_ONLY, QueryKind.UNKNOWN):
        add_text_match(query_text, boost=1.0)
    else:
        add_text_match(query_text, boost=1.0)

    if transliterated and transliterated != query_text:
        add_phonetic_should(transliterated, boost=0.7)

    return base_query


def _serialize_kind(kind_value: QueryKind | str | None) -> str:
    if isinstance(kind_value, QueryKind):
        return kind_value.value
    return str(kind_value or QueryKind.UNKNOWN.value)


def search_products(raw_query: str) -> Dict[str, object]:
    normalized_query = raw_query or ""
    cache_key = hash_query(normalized_query)
    cache_start = perf_counter()
    cached = cache.get(cache_key)
    if cached is not None:
        total_ms = (perf_counter() - cache_start) * 1000
        logger.info(
            "timing: total=%.2fms cache_hit=1 q=%r kind=%s",
            total_ms,
            normalized_query,
            cached.get("classification"),
        )
        return cached

    t0 = perf_counter()
    classification = classify_query(normalized_query)
    t1 = perf_counter()
    query_body = build_es_query(normalized_query, classification)
    t2 = perf_counter()
    es_response = search_es(query_body)
    t3 = perf_counter()

    hits = es_response.get("hits", {}).get("hits", [])
    results = [
        {
            "id": hit.get("_source", {}).get("id"),
            "manufacturer": hit.get("_source", {}).get("manufacturer"),
            "product_code": hit.get("_source", {}).get("product_code"),
            "title": hit.get("_source", {}).get("title"),
            "score": hit.get("_score"),
        }
        for hit in hits
    ]
    t4 = perf_counter()

    classify_ms = (t1 - t0) * 1000
    build_ms = (t2 - t1) * 1000
    es_ms = (t3 - t2) * 1000
    post_ms = (t4 - t3) * 1000
    total_ms = (t4 - t0) * 1000
    kind_serialized = _serialize_kind(classification.get("kind"))
    logger.info(
        "timing: total=%.2fms classify=%.2fms build=%.2fms es=%.2fms post=%.2fms q=%r kind=%s brands=%s",
        total_ms,
        classify_ms,
        build_ms,
        es_ms,
        post_ms,
        normalized_query,
        kind_serialized,
        classification.get("brands", []),
    )

    response = {
        "query": normalized_query,
        "results": results,
        "took_ms": es_ms,
        "eta_ms": total_ms,
        "classification": kind_serialized,
    }
    cache.set(cache_key, response, settings.cache_ttl_seconds)
    logger.debug("cache_store q=%r ttl=%s", normalized_query, settings.cache_ttl_seconds)
    return response
