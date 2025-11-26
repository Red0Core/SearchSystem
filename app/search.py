"""Search API that mirrors the legacy Java SearchService semantics."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

from elasticsearch import Elasticsearch

from .phonetics import normalize_text, to_phonetic

logger = logging.getLogger(__name__)

TEXT_FIELDS = [
    "title^3",
    "title.russian^2",
    "title.english^2",
    "title.autocomplete^1.5",
    "manufacturer^2",
    "manufacturer.autocomplete^1.5",
]
PHONETIC_FIELDS = ["title.phonetic^2", "manufacturer.phonetic^2", "phonetic"]
CODE_FIELDS = ["productCode^2", "productCode.numeric"]


def _build_query(normalized_q: str, phonetic_q: str | None, limit: int) -> Dict[str, Any]:
    should: List[dict] = []

    should.append(
        {
            "multi_match": {
                "query": normalized_q,
                "fields": TEXT_FIELDS,
                "type": "most_fields",
                "operator": "and",
                "fuzziness": "AUTO",
                "boost": 2.0,
            }
        }
    )

    if phonetic_q:
        should.append(
            {
                "multi_match": {
                    "query": phonetic_q,
                    "fields": PHONETIC_FIELDS,
                    "type": "most_fields",
                    "boost": 1.5,
                }
            }
        )

    should.append(
        {
            "multi_match": {
                "query": normalized_q,
                "fields": CODE_FIELDS,
                "fuzziness": "AUTO",
                "boost": 1.2,
            }
        }
    )

    should.append({"match_all": {"boost": 0.01}})

    return {
        "size": limit,
        "query": {
            "bool": {
                "should": should,
                "minimum_should_match": 1,
            }
        },
    }


async def search_products(es: Elasticsearch, index: str, q: str, limit: int = 50) -> dict:
    normalized_q = normalize_text(q)
    phonetic_q = to_phonetic(normalized_q) if normalized_q else ""
    query_body = _build_query(normalized_q, phonetic_q, limit)

    response = await asyncio.to_thread(es.search, index=index, body=query_body)
    hits = response.get("hits", {}).get("hits", [])
    results = [
        {
            **(hit.get("_source", {})),
            "score": hit.get("_score"),
        }
        for hit in hits
    ]
    took_ms = response.get("took", 0)
    logger.info(
        "search q=%r normalized=%r phonetic=%r hits=%s took=%sms",
        q,
        normalized_q,
        phonetic_q,
        len(results),
        took_ms,
    )
    return {
        "query": normalized_q,
        "results": results,
        "took_ms": took_ms,
    }
