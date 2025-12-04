"""Application configuration and constants."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _get_env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value is not None else default


@dataclass(frozen=True)
class Settings:
    """Simple settings container with environment variable overrides."""

    es_host: str = _get_env("ES_HOST", "http://localhost:9200")
    es_index: str = _get_env("ES_INDEX", "products")
    mapping_path: str = _get_env("MAPPING_PATH", "product-mapping.json")
    synonyms_path: str = _get_env("SYNONYMS_PATH", "config/brand_synonyms.txt")
    offers_path: str = _get_env("OFFERS_PATH", "offers.json")
    load_on_startup: bool = _get_env("LOAD_ON_STARTUP", "true").lower() in {"1", "true", "yes"}
    log_level: str = _get_env("LOG_LEVEL", "INFO")


settings = Settings()
