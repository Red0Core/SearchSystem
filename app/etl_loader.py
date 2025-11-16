"""ETL helpers for loading offers.json into Elasticsearch."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .brands import init_brands
from .config import settings
from .data_files import ensure_data_file
from .es_client import create_index_if_not_exists, index_documents
from .utils import normalize_code, normalize_manufacturer, transliterate_query

logger = logging.getLogger(__name__)

DATA_FILE = Path("offers.json")


def _prepare_document(raw: dict) -> dict:
    manufacturer = raw.get("manufacturer", "")
    product_code = raw.get("product_code", "")
    title = raw.get("title", "")
    search_text = " ".join(part for part in [manufacturer, product_code, title] if part)
    manufacturer_normalized = normalize_manufacturer(manufacturer)
    document = {
        "id": raw["id"],
        "manufacturer": manufacturer,
        "product_code": product_code,
        "title": title,
        "search_text": search_text,
        "search_text_tr": transliterate_query(search_text),
        "product_code_normalized": normalize_code(product_code),
    }
    if manufacturer_normalized:
        document["manufacturer_normalized"] = manufacturer_normalized
    return document


def load_offers_to_es() -> int:
    init_brands()
    data_file = ensure_data_file(DATA_FILE, settings.offers_source_url or None)
    with data_file.open("r", encoding="utf-8") as fh:
        raw_offers = json.load(fh)
    documents = [_prepare_document(item) for item in raw_offers]
    create_index_if_not_exists()
    logger.info("Indexing %s offers", len(documents))
    index_documents(documents)
    return len(documents)
