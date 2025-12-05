"""Search API that mirrors the legacy Java SearchService semantics."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

from elasticsearch import Elasticsearch

from .phonetics import normalize_query, to_phonetic, transliterate_text

logger = logging.getLogger(__name__)

TEXT_FIELDS = [
    "title^3",
    "title.russian^2",
    "title.english^2",
    "title.autocomplete^1.5",
    "titleTranslit^2",
    "titleTranslit.autocomplete^1.5",
    "manufacturer^2",
    "manufacturer.autocomplete^1.5",
]
PHONETIC_FIELDS = [
    "title.phonetic^2",
    "titleTranslit.phonetic^1.5",
    "titlePhonetic^1.25",
    "manufacturer.phonetic^2",
    "phonetic",
]
CODE_FIELDS = ["productCode^2", "productCode.numeric"]


def _build_query(normalized_q: str, transliterated_q: str, phonetic_q: str | None, limit: int) -> Dict[str, Any]:
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

    if transliterated_q:
        should.append(
            {
                "multi_match": {
                    "query": transliterated_q,
                    "fields": ["titleTranslit^2", "titleTranslit.autocomplete^1.25"],
                    "type": "most_fields",
                    "operator": "and",
                    "fuzziness": "AUTO",
                    "boost": 1.6,
                }
            }
        )

        should.append(
            {
                "match": {
                    "titleTranslit": {
                        "query": transliterated_q,
                        "operator": "or",
                        "minimum_should_match": "66%",
                        "fuzziness": "AUTO",
                        "boost": 1.1,
                    }
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

    query = {
        "size": limit,
        "query": {
            "bool": {
                "should": should,
                "minimum_should_match": 1,
            }
        },
    }

    logger.debug("ES query payload=%s", query)
    return query


async def search_products(es: Elasticsearch, index: str, q: str, limit: int = 50) -> dict:
    # Step 1: normalize raw user input (Russian/English) with collapsing repeats
    # and light synonym handling so phonetics and analyzers see a clean string.
    normalized_q = normalize_query(q)
    # Step 2: transliterate the normalized string for Latin-friendly matching.
    transliterated_q = transliterate_text(normalized_q)
    # Step 3: derive a phonetic key from the normalized string.
    phonetic_q = to_phonetic(normalized_q) if normalized_q else ""
    query_body = _build_query(normalized_q, transliterated_q, phonetic_q, limit)

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
        "search q=%r normalized=%r translit=%r phonetic=%r hits=%s took=%sms",
        q,
        normalized_q,
        transliterated_q,
        phonetic_q,
        len(results),
        took_ms,
    )
    return {
        "query": normalized_q,
        "results": results,
        "took_ms": took_ms,
    }
