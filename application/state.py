"""
Runtime in-memory state and initialization.

Backward-compatible re-exports keep all existing import sites working.
"""

import asyncio
import logging
import time
from typing import Dict, Optional

from application.free_uses import (  # noqa: F401
    FREE_USES_LIMIT,
    get_free_uses,
    get_free_uses_async,
    increment_free_uses,
    increment_free_uses_async,
    set_free_uses,
    set_free_uses_async,
)
from application.migration import migrate_legacy_data  # noqa: F401
from application.oauth_state import (  # noqa: F401
    delete_oauth_token_async,
    get_oauth_token_async,
    get_or_create_user,
    set_oauth_token_async,
)
from application.user_settings import (  # noqa: F401
    clear_user_setting,
    clear_user_setting_async,
    clear_user_settings_section,
    clear_user_settings_section_async,
    get_user_setting,
    get_user_setting_async,
    get_user_setting_json,
    get_user_setting_json_async,
    set_user_setting,
    set_user_setting_async,
    set_user_setting_json,
    set_user_setting_json_async,
)
from infrastructure.database import get_db
from infrastructure.database.database import Database
from shared.config import ALLOWED_USER_IDS, DEFAULT_LANGUAGE, YT_CACHE_TTL

logger = logging.getLogger(__name__)

# ── In-memory runtime state ────────────────────────────────────────────────────

active_tasks: Dict[int, asyncio.Task] = {}
yt_transcripts: Dict[str, dict] = {}
user_modes: Dict[int, str] = {}
groq_limits: dict = {}

# In-memory language cache
_user_languages: Dict[int, str] = {}


def update_groq_limits(headers: dict) -> None:
    """Update Groq rate limit cache from response headers."""
    global groq_limits
    groq_limits = {
        "limit_req": headers.get("x-ratelimit-limit-requests"),
        "remaining_req": headers.get("x-ratelimit-remaining-requests"),
        "reset_req": headers.get("x-ratelimit-reset-requests"),
        "limit_tokens": headers.get("x-ratelimit-limit-tokens"),
        "remaining_tokens": headers.get("x-ratelimit-remaining-tokens"),
        "reset_tokens": headers.get("x-ratelimit-reset-tokens"),
    }


async def can_use_shared_credentials(user_id: int) -> bool:
    """Return True if the user may use the bot's global (shared) API keys."""
    if not ALLOWED_USER_IDS:
        return True
    if user_id in ALLOWED_USER_IDS:
        return True
    if await get_user_setting_async(user_id, "llm_api_key"):
        return True
    return False


def cleanup_yt_cache() -> None:
    """Remove expired entries from yt_transcripts."""
    now = time.time()
    expired = [k for k, v in yt_transcripts.items() if now - v["ts"] > YT_CACHE_TTL]
    for k in expired:
        del yt_transcripts[k]


# ── Mode / language ────────────────────────────────────────────────────────────


async def get_mode(user_id: int) -> str:
    """Get user's current mode."""
    if user_id in user_modes:
        return user_modes[user_id]
    mode = await get_user_setting_async(user_id, "mode", "chat")
    user_modes[user_id] = mode
    return mode


async def set_mode(user_id: int, mode: str) -> None:
    """Set user's current mode."""
    await set_user_setting_async(user_id, "mode", mode)
    user_modes[user_id] = mode


async def get_language(user_id: int) -> str:
    """Get user's language preference."""
    if user_id in _user_languages:
        return _user_languages[user_id]
    lang = await get_user_setting_async(user_id, "language", DEFAULT_LANGUAGE)
    _user_languages[user_id] = lang
    return lang


async def set_language(user_id: int, language: str) -> None:
    """Set user's language preference."""
    await set_user_setting_async(user_id, "language", language)
    _user_languages[user_id] = language


# ── Initialization ─────────────────────────────────────────────────────────────

_db: Optional[Database] = None


def _get_db() -> Database:
    global _db
    if _db is None:
        _db = get_db()
    return _db


async def initialize_state() -> None:
    """Initialize database and migrate legacy data."""
    db = _get_db()
    await db.init_db()
    await migrate_legacy_data()

    # Initialize Redis connection and verify connectivity
    from infrastructure.redis_client import ping_redis

    redis_ok = await ping_redis()
    if redis_ok:
        logger.info("State system initialized (SQLite backend + Redis)")
    else:
        logger.warning("State system initialized (SQLite backend only - Redis unavailable)")


async def shutdown_state() -> None:
    """Close database and Redis connections."""
    db = _get_db()
    await db.close()
    from infrastructure.redis_client import close_redis

    await close_redis()


# Legacy alias
load_user_settings = initialize_state
