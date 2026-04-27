import os
import time
import hashlib
import json
from typing import Any, Optional

import diskcache

_cache: Optional[diskcache.Cache] = None


def _get_cache() -> diskcache.Cache:
    global _cache
    if _cache is None:
        from app.config import cache_dir
        _cache = diskcache.Cache(cache_dir())
    return _cache


def get(key: str) -> Optional[Any]:
    return _get_cache().get(key)


def set(key: str, value: Any, ttl: int = 86400):
    _get_cache().set(key, value, expire=ttl)


def get_image_path(url: str) -> Optional[str]:
    """Return cached local image path for a URL, or None if not cached."""
    key = "img:" + hashlib.md5(url.encode()).hexdigest()
    return _get_cache().get(key)


def set_image_path(url: str, local_path: str, ttl: int = 604800):
    """Cache a local image path for a URL (7-day TTL by default)."""
    key = "img:" + hashlib.md5(url.encode()).hexdigest()
    _get_cache().set(key, local_path, expire=ttl)


def api_key(query: str, source: str) -> str:
    return f"api:{source}:{hashlib.md5(query.encode()).hexdigest()}"
