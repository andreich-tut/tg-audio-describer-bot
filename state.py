"""
State module: Database-backed persistence with legacy JSON compatibility.

This module provides a drop-in replacement for the old in-memory state system.
All functions maintain the same API but now persist to SQLite database.

On startup, automatically migrates data from legacy data/user_settings.json.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from config import ALLOWED_USER_IDS, DEFAULT_LANGUAGE, MAX_HISTORY, YT_CACHE_TTL
from infrastructure.database import Database, get_db

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

FREE_USES_LIMIT = 3

# ── In-memory state (for runtime data) ────────────────────────────────────────

# Active task handles (for cancellation)
active_tasks: Dict[int, asyncio.Task] = {}

# YouTube transcript cache
yt_transcripts: Dict[str, dict] = {}

# User-specific GDocs settings (in-memory cache)
user_gdocs: Dict[int, bool] = {}

# User modes cache (for fast access)
user_modes: Dict[int, str] = {}

# ── Helper functions ──────────────────────────────────────────────────────────


def can_use_shared_credentials(user_id: int) -> bool:
    """Return True if the user may use the bot's global (shared) API keys."""
    # No access control configured → open/private bot, no free-tier limiting
    if not ALLOWED_USER_IDS:
        return True
    # Explicitly trusted users always have unlimited access
    if user_id in ALLOWED_USER_IDS:
        return True
    # User has own LLM credentials → no limit
    if get_user_setting(user_id, "llm_api_key"):
        return True
    return False


def cleanup_yt_cache():
    """Remove expired entries from yt_transcripts."""
    import time

    now = time.time()
    expired = [k for k, v in yt_transcripts.items() if now - v["ts"] > YT_CACHE_TTL]
    for k in expired:
        del yt_transcripts[k]


# ── Database initialization ──────────────────────────────────────────────────

_db: Optional[Database] = None


def _get_db() -> Database:
    """Get or initialize database connection."""
    global _db
    if _db is None:
        _db = get_db()
    return _db


# ── Legacy JSON file migration ───────────────────────────────────────────────

_JSON_FILE = Path(__file__).parent / "data" / "user_settings.json"


async def migrate_legacy_data() -> bool:
    """Migrate data from legacy JSON file to SQLite.

    Returns True if migration was performed, False if no legacy data found.
    """
    if not _JSON_FILE.exists():
        return False

    try:
        json_data = json.loads(_JSON_FILE.read_text(encoding="utf-8"))
        if not json_data:
            return False

        db = _get_db()
        migrated = await db.migrate_from_json(json_data)
        logger.info("Migrated %d users from legacy JSON to SQLite", migrated)

        # Archive the old file (don't delete, just rename)
        archive_path = _JSON_FILE.with_suffix(".json.archived")
        _JSON_FILE.rename(archive_path)
        logger.info("Archived legacy JSON file to %s", archive_path)

        return True
    except Exception as e:
        logger.error("Failed to migrate legacy data: %s", e)
        return False


# ── User operations ──────────────────────────────────────────────────────────


async def get_or_create_user(user_id: int, username: Optional[str] = None):
    """Get or create a user in the database."""
    db = _get_db()
    return await db.get_or_create_user(user_id, username)


# ── Settings operations (backward compatible API) ────────────────────────────


def get_user_setting(user_id: int, key: str, default=None):
    """Get a user setting (synchronous wrapper)."""
    db = _get_db()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # No event loop running
        return asyncio.run(db.get_setting(user_id, key, default))
    else:
        if loop.is_running():
            # Event loop is running (in async context) - return future
            import warnings

            warnings.warn(
                "get_user_setting called in async context without await. Use await get_user_setting_async() instead.",
                RuntimeWarning,
            )
            return default
        return loop.run_until_complete(db.get_setting(user_id, key, default))


async def get_user_setting_async(user_id: int, key: str, default=None):
    """Get a user setting (async version)."""
    db = _get_db()
    return await db.get_setting(user_id, key, default)


def set_user_setting(user_id: int, key: str, value: str) -> None:
    """Set a user setting (synchronous wrapper)."""
    import asyncio

    db = _get_db()
    # Determine if encryption is needed
    encrypt_value = key == "llm_api_key"

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        asyncio.run(db.set_setting(user_id, key, value, encrypt_value=encrypt_value))
    else:
        if loop.is_running():
            asyncio.create_task(db.set_setting(user_id, key, value, encrypt_value=encrypt_value))
        else:
            loop.run_until_complete(db.set_setting(user_id, key, value, encrypt_value=encrypt_value))


async def set_user_setting_async(user_id: int, key: str, value: str, encrypt_value: bool = False) -> None:
    """Set a user setting (async version)."""
    db = _get_db()
    await db.set_setting(user_id, key, value, encrypt_value=encrypt_value)


def set_user_setting_json(user_id: int, key: str, value: dict) -> None:
    """Store a JSON-serializable dict (e.g., OAuth token)."""
    import asyncio

    db = _get_db()
    # OAuth tokens should be encrypted
    encrypt_value = key == "yandex_oauth_token"

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        asyncio.run(db.set_setting_json(user_id, key, value, encrypt_value=encrypt_value))
    else:
        if loop.is_running():
            asyncio.create_task(db.set_setting_json(user_id, key, value, encrypt_value=encrypt_value))
        else:
            loop.run_until_complete(db.set_setting_json(user_id, key, value, encrypt_value=encrypt_value))


async def set_user_setting_json_async(user_id: int, key: str, value: dict, encrypt_value: bool = False) -> None:
    """Store a JSON-serializable dict (async version)."""
    db = _get_db()
    await db.set_setting_json(user_id, key, value, encrypt_value=encrypt_value)


def get_user_setting_json(user_id: int, key: str, default=None):
    """Retrieve a JSON-serializable dict (e.g., OAuth token)."""
    import asyncio

    db = _get_db()

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return asyncio.run(db.get_setting_json(user_id, key, default))
    else:
        if loop.is_running():
            import warnings

            warnings.warn(
                "get_user_setting_json called in async context without await. "
                "Use await get_user_setting_json_async() instead.",
                RuntimeWarning,
            )
            return default
        return loop.run_until_complete(db.get_setting_json(user_id, key, default))


async def get_user_setting_json_async(user_id: int, key: str, default=None):
    """Retrieve a JSON-serializable dict (async version)."""
    db = _get_db()
    return await db.get_setting_json(user_id, key, default)


def clear_user_setting(user_id: int, key: str) -> None:
    """Delete a single user setting."""
    import asyncio

    db = _get_db()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        asyncio.run(db.delete_setting(user_id, key))
    else:
        if loop.is_running():
            asyncio.create_task(db.delete_setting(user_id, key))
        else:
            loop.run_until_complete(db.delete_setting(user_id, key))


async def clear_user_setting_async(user_id: int, key: str) -> bool:
    """Delete a single user setting (async version)."""
    db = _get_db()
    return await db.delete_setting(user_id, key)


def clear_user_settings_section(user_id: int, keys: list[str]) -> None:
    """Delete multiple user settings by keys."""
    import asyncio

    db = _get_db()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        asyncio.run(db.delete_settings_section(user_id, keys))
    else:
        if loop.is_running():
            asyncio.create_task(db.delete_settings_section(user_id, keys))
        else:
            loop.run_until_complete(db.delete_settings_section(user_id, keys))


async def clear_user_settings_section_async(user_id: int, keys: list[str]) -> int:
    """Delete multiple user settings by keys (async version)."""
    db = _get_db()
    return await db.delete_settings_section(user_id, keys)


# ── OAuth token operations ────────────────────────────────────────────────────


async def get_oauth_token_async(user_id: int, provider: str) -> Optional[dict]:
    """Get OAuth tokens for a user."""
    db = _get_db()
    return await db.get_oauth_token(user_id, provider)


async def set_oauth_token_async(
    user_id: int,
    provider: str,
    access_token: str,
    refresh_token: Optional[str] = None,
    expires_at: Optional[datetime] = None,
    meta: Optional[dict] = None,
) -> None:
    """Set OAuth tokens for a user."""
    db = _get_db()
    await db.set_oauth_token(user_id, provider, access_token, refresh_token, expires_at, meta)


async def delete_oauth_token_async(user_id: int, provider: str) -> bool:
    """Delete OAuth tokens for a user."""
    db = _get_db()
    return await db.delete_oauth_token(user_id, provider)


# ── Conversation history operations ──────────────────────────────────────────


# Keep backward compatible sync wrappers
def add_to_history(user_id: int, role: str, content: str) -> None:
    """Add a message to conversation history (sync wrapper)."""
    import asyncio

    db = _get_db()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        asyncio.run(_add_history_impl(db, user_id, role, content))
    else:
        if loop.is_running():
            asyncio.create_task(_add_history_impl(db, user_id, role, content))
        else:
            loop.run_until_complete(_add_history_impl(db, user_id, role, content))


async def _add_history_impl(db: Database, user_id: int, role: str, content: str) -> None:
    """Implementation of add_to_history."""
    await db.add_conversation_message(user_id, role, content)

    # Trim history to MAX_HISTORY
    history = await db.get_conversation_history(user_id, limit=MAX_HISTORY + 5)
    if len(history) > MAX_HISTORY:
        to_delete = len(history) - MAX_HISTORY
        async with db.async_session_maker() as session:
            from sqlalchemy import delete, select

            from infrastructure.database.models import Conversation

            result = await session.execute(
                select(Conversation.id)
                .where(Conversation.user_id == user_id)
                .order_by(Conversation.timestamp.asc())
                .limit(to_delete)
            )
            ids_to_delete = result.scalars().all()
            if ids_to_delete:
                await session.execute(delete(Conversation).where(Conversation.id.in_(ids_to_delete)))
                await session.commit()


async def add_to_history_async(user_id: int, role: str, content: str) -> None:
    """Add a message to conversation history."""
    db = _get_db()
    await db.add_conversation_message(user_id, role, content)

    # Trim history to MAX_HISTORY
    history = await db.get_conversation_history(user_id, limit=MAX_HISTORY + 5)
    if len(history) > MAX_HISTORY:
        to_delete = len(history) - MAX_HISTORY
        async with db.async_session_maker() as session:
            from sqlalchemy import delete, select

            from infrastructure.database.models import Conversation

            result = await session.execute(
                select(Conversation.id)
                .where(Conversation.user_id == user_id)
                .order_by(Conversation.timestamp.asc())
                .limit(to_delete)
            )
            ids_to_delete = result.scalars().all()
            if ids_to_delete:
                await session.execute(delete(Conversation).where(Conversation.id.in_(ids_to_delete)))
                await session.commit()


async def get_history_async(user_id: int) -> list[dict]:
    """Get conversation history for a user."""
    db = _get_db()
    return await db.get_conversation_history(user_id, limit=MAX_HISTORY)


def get_history(user_id: int) -> list[dict]:
    """Get conversation history for a user (sync wrapper)."""
    import asyncio

    db = _get_db()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return asyncio.run(db.get_conversation_history(user_id, limit=MAX_HISTORY))
    else:
        if loop.is_running():
            return []
        return loop.run_until_complete(db.get_conversation_history(user_id, limit=MAX_HISTORY))


async def clear_history_async(user_id: int) -> int:
    """Clear conversation history for a user."""
    db = _get_db()
    return await db.clear_conversation(user_id)


def clear_history(user_id: int) -> int:
    """Clear conversation history for a user (sync wrapper)."""
    import asyncio

    db = _get_db()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return asyncio.run(db.clear_conversation(user_id))
    else:
        if loop.is_running():
            return 0
        return loop.run_until_complete(db.clear_conversation(user_id))


# ── Free uses operations ─────────────────────────────────────────────────────


def get_free_uses(user_id: int) -> int:
    """Get free uses count for a user."""
    import asyncio

    db = _get_db()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return asyncio.run(db.get_free_uses(user_id))
    else:
        if loop.is_running():
            return 0  # Default in async context
        return loop.run_until_complete(db.get_free_uses(user_id))


async def get_free_uses_async(user_id: int) -> int:
    """Get free uses count for a user (async version)."""
    db = _get_db()
    return await db.get_free_uses(user_id)


def set_free_uses(user_id: int, count: int) -> None:
    """Set free uses count for a user."""
    import asyncio

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
    import asyncio

    db = _get_db()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return asyncio.run(db.increment_free_uses(user_id))
    else:
        if loop.is_running():
            # Can't run async in async context, return 0 as fallback
            return 0
        return loop.run_until_complete(db.increment_free_uses(user_id))


# ── User mode/language operations (backward compatible) ──────────────────────

# In-memory caches for frequently accessed data
_user_languages: Dict[int, str] = {}


def get_mode(user_id: int) -> str:
    """Get user's current mode."""
    if user_id in user_modes:
        return user_modes[user_id]
    mode = get_user_setting(user_id, "mode", "chat")
    user_modes[user_id] = mode
    return mode


def set_mode(user_id: int, mode: str) -> None:
    """Set user's current mode."""
    set_user_setting(user_id, "mode", mode)
    user_modes[user_id] = mode


def get_language(user_id: int) -> str:
    """Get user's language preference."""
    if user_id in _user_languages:
        return _user_languages[user_id]
    lang = get_user_setting(user_id, "language", DEFAULT_LANGUAGE)
    _user_languages[user_id] = lang
    return lang


def set_language(user_id: int, language: str) -> None:
    """Set user's language preference."""
    set_user_setting(user_id, "language", language)
    _user_languages[user_id] = language


# ── Initialization ────────────────────────────────────────────────────────────


async def initialize_state() -> None:
    """Initialize database and migrate legacy data."""
    db = _get_db()
    await db.init_db()
    await migrate_legacy_data()
    logger.info("State system initialized (SQLite backend)")


async def shutdown_state() -> None:
    """Close database connections."""
    db = _get_db()
    await db.close()


# ── Legacy compatibility ─────────────────────────────────────────────────────

# Keep old function name for backward compatibility
load_user_settings = initialize_state
