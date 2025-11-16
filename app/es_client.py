"""Elasticsearch client helpers."""
from __future__ import annotations

import logging
from typing import Iterable

from elasticsearch import Elasticsearch, helpers
from elasticsearch.exceptions import NotFoundError

from .config import settings

logger = logging.getLogger(__name__)

_client: Elasticsearch | None = None


INDEX_BODY = {
    "settings": {
        "analysis": {
            "filter": {
                "russian_stop": {
                    "type": "stop",
                    "stopwords": "_russian_",
                },
                "russian_stemmer": {
                    "type": "stemmer",
                    "language": "russian",
                },
                "english_stop": {
                    "type": "stop",
                    "stopwords": "_english_",
                },
                "english_stemmer": {
                    "type": "stemmer",
                    "language": "english",
                },
                "brand_phonetic": {
                    "type": "phonetic",
                    "encoder": "double_metaphone",
                    "replace": True,
                }
            },
            "analyzer": {
                "ru_en_search": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": [
                        "lowercase",
                        "russian_stop",
                        "english_stop",
                        "russian_stemmer",
                        "english_stemmer",
                        "asciifolding",
                    ],
                },
                "brand_phonetic_analyzer": {
                    "tokenizer": "standard",
                    "filter": ["lowercase", "brand_phonetic"],
                },
            },
        }
    },
    "mappings": {
        "properties": {
            "id": {"type": "keyword"},
            "manufacturer": {
                "type": "text",
                "analyzer": "ru_en_search",
                "fields": {
                    "phonetic": {
                        "type": "text",
                        "analyzer": "brand_phonetic_analyzer",
                    },
                    "keyword": {"type": "keyword", "ignore_above": 256},
                },
            },
            "product_code": {"type": "keyword"},
            "title": {
                "type": "text",
                "analyzer": "ru_en_search",
                "fields": {
                    "phonetic": {
                        "type": "text",
                        "analyzer": "brand_phonetic_analyzer",
                    }
                },
            },
            "search_text": {"type": "text", "analyzer": "ru_en_search"},
            "search_text_tr": {"type": "text", "analyzer": "standard"},
            "product_code_normalized": {"type": "keyword"},
            "manufacturer_normalized": {"type": "keyword"},
        }
    },
}


def get_client() -> Elasticsearch:
    global _client
    if _client is None:
        logger.info("Connecting to Elasticsearch at %s", settings.es_host)
        _client = Elasticsearch(settings.es_host)
    return _client


def create_index_if_not_exists() -> None:
    client = get_client()
    if client.indices.exists(index=settings.es_index):
        return
    logger.info("Creating index %s", settings.es_index)
    client.indices.create(index=settings.es_index, body=INDEX_BODY)


def index_documents(documents: Iterable[dict]) -> None:
    client = get_client()
    actions = (
        {
            "_index": settings.es_index,
            "_id": doc["id"],
            "_source": doc,
        }
        for doc in documents
    )
    helpers.bulk(client, actions)


def search_es(query_body: dict) -> dict:
    client = get_client()
    return client.search(index=settings.es_index, body=query_body)


def index_is_empty() -> bool:
    client = get_client()
    try:
        stats = client.count(index=settings.es_index)
        return stats.get("count", 0) == 0
    except NotFoundError:
        return True
