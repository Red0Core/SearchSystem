"""Elasticsearch client factory.

The rest of the code works against the official synchronous client. Blocking
calls are wrapped via ``asyncio.to_thread`` by the caller where necessary.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from elasticsearch import Elasticsearch

from .config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_client() -> Elasticsearch:
    logger.info("Connecting to Elasticsearch at %s", settings.es_host)
    return Elasticsearch(settings.es_host)
