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
    redis_host: str = _get_env("REDIS_HOST", "localhost")
    redis_port: int = int(_get_env("REDIS_PORT", "6379"))
    cache_ttl_seconds: int = int(_get_env("CACHE_TTL_SECONDS", "300"))
    load_on_startup: bool = _get_env("LOAD_ON_STARTUP", "true").lower() in {"1", "true", "yes"}
    search_result_size: int = int(_get_env("SEARCH_RESULT_SIZE", "100"))
    brand_result_size: int = int(_get_env("BRAND_RESULT_SIZE", "30"))
    brand_fallback_min_hits: int = int(_get_env("BRAND_FALLBACK_MIN_HITS", "3"))
    offers_source_url: str = _get_env("OFFERS_SOURCE_URL", "")
    manufacturers_source_url: str = _get_env("MANUFACTURERS_SOURCE_URL", "")


settings = Settings()
