"""Search logic built on top of Elasticsearch."""
from __future__ import annotations

import logging
from time import perf_counter
from typing import Dict, List

from .cache import get_cache
from .config import settings
from .es_client import search_es
from .utils import classify_query, hash_query, normalize_code, transliterate_query

logger = logging.getLogger(__name__)
cache = get_cache()


def build_es_query(raw_query: str, classification: Dict[str, object]) -> dict:
    base_query = {
        "size": settings.search_result_size,
        "query": {
            "bool": {
                "should": [],
                "minimum_should_match": 1,
            }
        },
    }
    bool_clause = base_query["query"]["bool"]

    query_text = classification.get("query", raw_query)
    transliterated = transliterate_query(query_text)

    def add_should(clause: dict) -> None:
        bool_clause["should"].append(clause)

    if classification["type"] == "article":
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

    if classification["type"] == "url":
        tokens: List[str] = classification.get("tokens", [])
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

    # Generic text query with fuzzy, transliteration, brand boost, and phonetic fallbacks
    add_should(
        {
            "multi_match": {
                "query": query_text,
                "fields": ["title^3", "manufacturer^2", "search_text"],
                "fuzziness": "AUTO",
            }
        }
    )
    add_should(
        {
            "multi_match": {
                "query": query_text,
                "fields": ["manufacturer.phonetic^2", "title.phonetic"],
                "type": "most_fields",
                "boost": 0.7,
            }
        }
    )
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

    brand_canonical = classification.get("brand_canonical")
    brand_token = classification.get("brand_token")
    if brand_canonical:
        add_should(
            {"term": {"manufacturer_normalized": {"value": brand_canonical, "boost": 5}}}
        )
        add_should(
            {
                "multi_match": {
                    "query": brand_token or query_text,
                    "fields": ["manufacturer.phonetic^4"],
                    "type": "most_fields",
                    "boost": 1.5,
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
    response = {
        "query": raw_query,
        "results": results,
        "took_ms": took_ms,
        "eta_ms": took_ms,
    }
    cache.set(cache_key, response, settings.cache_ttl_seconds)
    return response
