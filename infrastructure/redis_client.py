"""
Redis connection singleton for pub/sub and caching.
"""

import asyncio
import logging
from typing import Optional

import redis.asyncio as redis

from shared.config import REDIS_URL

logger = logging.getLogger(__name__)

_pool: Optional[redis.Redis] = None
_MAX_RETRIES = 5
_RETRY_DELAY = 2.0  # seconds


async def get_redis() -> redis.Redis:
    """Get or create Redis connection with retry logic."""
    global _pool
    if _pool is None:
        for attempt in range(_MAX_RETRIES):
            try:
                _pool = redis.from_url(
                    REDIS_URL,
                    decode_responses=True,
                    max_connections=50,
                    socket_connect_timeout=5.0,
                    socket_keepalive=True,
                )
                # Verify connection
                await _pool.ping()
                logger.info("Redis connected: %s", REDIS_URL)
                break
            except redis.ConnectionError as e:
                if attempt == _MAX_RETRIES - 1:
                    logger.error("Failed to connect to Redis after %d attempts: %s", _MAX_RETRIES, e)
                    raise
                logger.warning(
                    "Redis connection attempt %d/%d failed, retrying in %.1fs...",
                    attempt + 1,
                    _MAX_RETRIES,
                    _RETRY_DELAY,
                )
                await asyncio.sleep(_RETRY_DELAY)
    return _pool


async def ping_redis() -> bool:
    """Health check: ping Redis and return True if responsive."""
    try:
        r = await get_redis()
        await r.ping()
        return True
    except Exception as e:
        logger.warning("Redis ping failed: %s", e)
        return False


async def close_redis() -> None:
    """Close Redis connection."""
    global _pool
    if _pool:
        await _pool.aclose()
        _pool = None
        logger.info("Redis connection closed")
