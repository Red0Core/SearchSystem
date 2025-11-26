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


def _load_synonyms(path: Path) -> list[str]:
    """Read synonym rules from a file, ignoring blanks and comments."""

    try:
        with path.open("r", encoding="utf-8") as fh:
            return [line.strip() for line in fh if line.strip() and not line.lstrip().startswith("#")]
    except FileNotFoundError:
        logger.warning("Synonyms file %s not found; falling back to mapping defaults", path)
        return []


async def ensure_index(es: Elasticsearch) -> None:
    """Create the products index with custom analyzers if it is missing."""

    mapping_path = Path(settings.mapping_path)
    body = _load_mapping(mapping_path)
    brand_synonyms = _load_synonyms(Path(settings.synonyms_path))

    # Ensure the synonym filter works even when Elasticsearch cannot read the file
    # from its config directory (common in local/hosted setups without mounts).
    filters = body.get("settings", {}).get("analysis", {}).get("filter", {})
    brand_filter = filters.get("brand_synonyms", {})
    if brand_synonyms:
        brand_filter["synonyms"] = brand_synonyms
    brand_filter.pop("synonyms_path", None)
    filters["brand_synonyms"] = brand_filter

    exists = await asyncio.to_thread(es.indices.exists, index=settings.es_index)
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
