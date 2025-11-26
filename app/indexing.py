"""Index creation and maintenance helpers."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from elasticsearch import Elasticsearch
from elasticsearch.exceptions import BadRequestError, NotFoundError

from .config import settings

logger = logging.getLogger(__name__)


def _load_mapping(mapping_path: Path) -> dict:
    with mapping_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


async def ensure_index(es: Elasticsearch) -> None:
    """Create the products index with custom analyzers if it is missing."""

    mapping_path = Path(settings.mapping_path)
    body = _load_mapping(mapping_path)
    exists = await asyncio.to_thread(es.indices.exists, settings.es_index)
    if exists:
        return
    logger.info("Creating index %s using %s", settings.es_index, mapping_path)
    try:
        await asyncio.to_thread(es.indices.create, index=settings.es_index, body=body)
    except BadRequestError as exc:
        if getattr(exc, "error", "") == "resource_already_exists_exception":
            logger.info("Index %s already exists", settings.es_index)
            return
        logger.exception("Failed to create index: %s", exc)
        raise


async def drop_index(es: Elasticsearch) -> None:
    try:
        await asyncio.to_thread(es.indices.delete, index=settings.es_index)
    except NotFoundError:
        return


async def index_is_empty(es: Elasticsearch) -> bool:
    try:
        stats = await asyncio.to_thread(es.count, index=settings.es_index)
        return stats.get("count", 0) == 0
    except NotFoundError:
        return True
