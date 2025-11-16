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


def build_es_query(raw_query: str, classification: QueryClassification) -> dict:
    base_query = {
        "size": settings.search_result_size,
        "query": {"bool": {"should": [], "minimum_should_match": 1}},
    }
    bool_clause = base_query["query"]["bool"]

    query_text = classification.get("query", raw_query) or raw_query
    transliterated = transliterate_query(query_text)
    kind = classification.get("kind", QueryKind.UNKNOWN)

    def add_should(clause: dict) -> None:
        bool_clause["should"].append(clause)

    if kind == QueryKind.ARTICLE:
        normalized = classification.get("normalized_code") or normalize_code(query_text)
        if normalized:
            add_should({"term": {"product_code_normalized": {"value": normalized, "boost": 5}}})
        add_should(
            {
                "match": {
                    "product_code": {
                        "query": query_text,
                        "fuzziness": "AUTO",
                        "boost": 3,
                    }
                }
            }
        )
        add_should(
            {
                "match": {
                    "search_text": {
                        "query": query_text,
                        "fuzziness": "AUTO",
                        "boost": 2,
                    }
                }
            }
        )
        return base_query

    if kind == QueryKind.URL:
        tokens: List[str] = classification.get("url_tokens", [])
        if tokens:
            add_should(
                {
                    "multi_match": {
                        "query": " ".join(tokens),
                        "fields": ["search_text", "search_text_tr"],
                        "fuzziness": "AUTO",
                    }
                }
            )
        else:
            add_should({"match": {"search_text": {"query": query_text, "fuzziness": "AUTO"}}})
        return base_query

    brands: List[str] = classification.get("brands", [])
    brand_originals: Dict[str, str] = classification.get("brand_originals", {})
    generic_tokens: List[str] = classification.get("generic_tokens", [])
    generic_text = " ".join(generic_tokens) if generic_tokens else query_text

    def add_brand_terms(boost: float = 5.0) -> None:
        for brand in brands:
            add_should({"term": {"manufacturer_normalized": {"value": brand, "boost": boost}}})

    def add_brand_phonetic(boost: float = 1.5) -> None:
        brand_focus = " ".join(brand_originals.values()) or query_text
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

    def add_text_clauses(text: str, boost: float = 1.0) -> None:
        if not text:
            return
        add_should(
            {
                "multi_match": {
                    "query": text,
                    "fields": ["title^3", "search_text", "manufacturer"],
                    "fuzziness": "AUTO",
                    "boost": boost,
                }
            }
        )
        add_should(
            {
                "multi_match": {
                    "query": text,
                    "fields": ["manufacturer.phonetic^2", "title.phonetic"],
                    "type": "most_fields",
                    "boost": 0.7 * boost,
                }
            }
        )

    # Textual classes
    if kind == QueryKind.BRAND_ONLY:
        add_brand_terms(boost=5.0)
        add_brand_phonetic(boost=2.0)
        add_text_clauses(query_text, boost=0.8)
    elif kind == QueryKind.BRAND_WITH_GENERIC:
        add_brand_terms(boost=4.0)
        add_brand_phonetic(boost=1.5)
        add_text_clauses(query_text, boost=1.2)
        if generic_text and generic_text != query_text:
            add_text_clauses(generic_text, boost=1.0)
    elif kind in (QueryKind.GENERIC_ONLY, QueryKind.UNKNOWN):
        add_text_clauses(query_text, boost=1.0)
    else:
        add_text_clauses(query_text, boost=1.0)

    if transliterated and transliterated != query_text:
        add_should(
            {
                "multi_match": {
                    "query": transliterated,
                    "fields": ["search_text_tr", "search_text"],
                    "fuzziness": "AUTO",
                    "boost": 0.8,
                }
            }
        )

    return base_query


def search_products(raw_query: str) -> Dict[str, object]:
    cache_key = hash_query(raw_query)
    cached = cache.get(cache_key)
    if cached:
        logger.debug("Cache hit for query %s", raw_query)
        return cached

    classification = classify_query(raw_query)
    query_body = build_es_query(raw_query, classification)
    start = perf_counter()
    es_response = search_es(query_body)
    took_ms = (perf_counter() - start) * 1000
    hits = es_response.get("hits", {}).get("hits", [])
    results = [
        {
            "id": hit["_source"].get("id"),
            "manufacturer": hit["_source"].get("manufacturer"),
            "product_code": hit["_source"].get("product_code"),
            "title": hit["_source"].get("title"),
            "score": hit.get("_score"),
        }
        for hit in hits
    ]
    kind_value = classification.get("kind", QueryKind.UNKNOWN)
    if isinstance(kind_value, QueryKind):
        kind_serialized = kind_value.value
    else:
        kind_serialized = str(kind_value)
    response = {
        "query": raw_query,
        "results": results,
        "took_ms": took_ms,
        "eta_ms": took_ms,
        "classification": kind_serialized,
    }
    cache.set(cache_key, response, settings.cache_ttl_seconds)
    return response
