"""
Free-tier usage tracking.
"""

import asyncio
import logging

from infrastructure.database import get_db

logger = logging.getLogger(__name__)

FREE_USES_LIMIT = 3


def _get_db():
    return get_db()


def get_free_uses(user_id: int) -> int:
    """Get free uses count for a user."""
    db = _get_db()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return asyncio.run(db.get_free_uses(user_id))
    else:
        if loop.is_running():
            return 0
        return loop.run_until_complete(db.get_free_uses(user_id))


async def get_free_uses_async(user_id: int) -> int:
    """Get free uses count for a user (async version)."""
    db = _get_db()
    return await db.get_free_uses(user_id)


def set_free_uses(user_id: int, count: int) -> None:
    """Set free uses count for a user."""
    db = _get_db()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        asyncio.run(db.set_free_uses(user_id, count))
    else:
        if loop.is_running():
            asyncio.create_task(db.set_free_uses(user_id, count))
        else:
            loop.run_until_complete(db.set_free_uses(user_id, count))


async def set_free_uses_async(user_id: int, count: int) -> None:
    """Set free uses count for a user (async version)."""
    db = _get_db()
    await db.set_free_uses(user_id, count)


async def increment_free_uses_async(user_id: int) -> int:
    """Increment free uses count and return new value."""
    db = _get_db()
    return await db.increment_free_uses(user_id)


def increment_free_uses(user_id: int) -> int:
    """Increment free uses count and return new value (sync wrapper)."""
    db = _get_db()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return asyncio.run(db.increment_free_uses(user_id))
    else:
        if loop.is_running():
            return 0
        return loop.run_until_complete(db.increment_free_uses(user_id))
