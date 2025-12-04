"""Data importer that mirrors the legacy Java DataImporter behavior."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Iterable

from elasticsearch import Elasticsearch, helpers

from .config import settings
from .phonetics import normalize_query, to_phonetic

logger = logging.getLogger(__name__)


def _load_offers(path: Path) -> list[dict]:
    if not path.exists():
        logger.warning("Offers file %s is missing", path)
        return []
    # Detect Git LFS placeholder to avoid attempting to parse it as JSON.
    with path.open("r", encoding="utf-8") as fh:
        first_line = fh.readline()
        if first_line.startswith("version https://git-lfs.github.com/spec/v1"):
            logger.warning("Offers file %s is a Git LFS pointer; real data not downloaded", path)
            return []
        fh.seek(0)
        return json.load(fh)


def _prepare_product(raw: dict) -> dict:
    title = raw.get("title") or raw.get("name") or ""
    manufacturer = raw.get("manufacturer") or raw.get("brand") or ""
    product_code = raw.get("productCode") or raw.get("product_code") or raw.get("article") or ""
    external_id = str(raw.get("externalId") or raw.get("external_id") or raw.get("id") or product_code or title)

    phonetic_source = " ".join(part for part in (title, manufacturer) if part)
    normalized_phonetic_source = normalize_query(phonetic_source)
    phonetic = to_phonetic(normalized_phonetic_source)

    product = {
        "title": title,
        "manufacturer": manufacturer,
        "productCode": product_code,
        "externalId": external_id,
        "phonetic": phonetic,
    }

    for field in ("price", "category", "currency"):
        if field in raw:
            product[field] = raw[field]
    return product


def _iter_actions(index: str, products: Iterable[dict]) -> Iterable[dict]:
    for product in products:
        yield {
            "_index": index,
            "_id": product.get("externalId") or product.get("productCode"),
            "_source": product,
        }


async def import_products(es: Elasticsearch) -> int:
    offers = _load_offers(Path(settings.offers_path))
    if not offers:
        return 0
    products = [_prepare_product(item) for item in offers]
    actions = list(_iter_actions(settings.es_index, products))
    await asyncio.to_thread(helpers.bulk, es, actions)
    return len(actions)


async def import_if_empty(es: Elasticsearch) -> int:
    stats = await asyncio.to_thread(es.count, index=settings.es_index)
    if stats.get("count", 0) > 0:
        return 0
    return await import_products(es)


async def reindex_data(es: Elasticsearch) -> int:
    from .indexing import drop_index, ensure_index

    await drop_index(es)
    await ensure_index(es)
    return await import_products(es)
