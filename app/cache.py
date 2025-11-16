"""Caching helpers with Redis primary and in-memory fallback."""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

import redis

from .config import settings

logger = logging.getLogger(__name__)


class CacheBackend(Protocol):
    def get(self, key: str) -> Optional[Dict[str, Any]]: ...

    def set(self, key: str, value: Dict[str, Any], ttl: int) -> None: ...


@dataclass
class RedisCache:
    client: redis.Redis

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        try:
            data = self.client.get(key)
        except redis.RedisError as exc:  # pragma: no cover - protective
            logger.warning("Redis get failed: %s", exc)
            return None
        if not data:
            return None
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return None

    def set(self, key: str, value: Dict[str, Any], ttl: int) -> None:
        try:
            self.client.setex(key, ttl, json.dumps(value))
        except redis.RedisError as exc:  # pragma: no cover - protective
            logger.warning("Redis set failed: %s", exc)


class InMemoryCache:
    def __init__(self) -> None:
        self._store: Dict[str, tuple[float, Dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            value = self._store.get(key)
            if not value:
                return None
            expires_at, payload = value
            if expires_at < time.time():
                self._store.pop(key, None)
                return None
            return payload

    def set(self, key: str, value: Dict[str, Any], ttl: int) -> None:
        with self._lock:
            self._store[key] = (time.time() + ttl, value)


_cache: CacheBackend | None = None


def get_cache() -> CacheBackend:
    global _cache
    if _cache is not None:
        return _cache
    try:
        client = redis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=False)
        client.ping()
        logger.info("Using Redis cache at %s:%s", settings.redis_host, settings.redis_port)
        _cache = RedisCache(client)
    except redis.RedisError:
        logger.warning("Redis not available, using in-memory cache")
        _cache = InMemoryCache()
    return _cache
