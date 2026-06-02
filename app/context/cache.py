"""
Clinova Penthus AI Engine - Redis Cache
Async Redis cache abstraction with connection pooling.
"""

import json
from typing import Any, Optional

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class CacheClient:
    """Async Redis cache client with JSON serialization."""

    def __init__(self, redis_url: Optional[str] = None):
        self.settings = get_settings()
        self.redis_url = redis_url or self.settings.redis.url
        self._redis: Optional[aioredis.Redis] = None

    async def connect(self) -> "CacheClient":
        """Initialize Redis connection."""
        try:
            self._redis = aioredis.from_url(
                self.redis_url,
                decode_responses=True,
                max_connections=self.settings.redis.pool_size,
                socket_timeout=self.settings.redis.socket_timeout,
                socket_connect_timeout=self.settings.redis.socket_connect_timeout,
                health_check_interval=self.settings.redis.health_check_interval,
            )
            # Test connection
            await self._redis.ping()
            logger.info("redis_connected", url=self.redis_url)
        except Exception as e:
            logger.error("redis_connection_failed", error=str(e))
            self._redis = None
        return self

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None
            logger.info("redis_disconnected")

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if not self._redis:
            return None
        try:
            value = await self._redis.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.warning("redis_get_failed", key=key, error=str(e))
            return None

    async def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        """Set value in cache with TTL."""
        if not self._redis:
            return
        try:
            serialized = json.dumps(value, default=str)
            await self._redis.setex(key, ttl, serialized)
        except Exception as e:
            logger.warning("redis_set_failed", key=key, error=str(e))

    async def delete(self, key: str) -> None:
        """Delete key from cache."""
        if not self._redis:
            return
        try:
            await self._redis.delete(key)
        except Exception as e:
            logger.warning("redis_delete_failed", key=key, error=str(e))

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        if not self._redis:
            return False
        try:
            return await self._redis.exists(key) > 0
        except Exception as e:
            logger.warning("redis_exists_failed", key=key, error=str(e))
            return False

    async def health_check(self) -> bool:
        """Check Redis connectivity."""
        if not self._redis:
            return False
        try:
            await self._redis.ping()
            return True
        except Exception:
            return False
