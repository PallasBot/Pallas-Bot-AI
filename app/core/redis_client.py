from __future__ import annotations

from functools import lru_cache

import redis

from app.core.config import settings


@lru_cache
def redis_client() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def ping_redis_sync() -> bool:
    try:
        return bool(redis_client().ping())
    except redis.RedisError:
        return False
