"""
User settings operations: get/set/clear individual settings and sections.
"""

import asyncio
import logging

from infrastructure.database import get_db

logger = logging.getLogger(__name__)


def _get_db():
    return get_db()


def get_user_setting(user_id: int, key: str, default=None):
    """Get a user setting (synchronous wrapper)."""
    db = _get_db()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return asyncio.run(db.get_setting(user_id, key, default))
    else:
        if loop.is_running():
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
    db = _get_db()
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
    """Store a JSON-serializable dict."""
    db = _get_db()
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
    """Retrieve a JSON-serializable dict."""
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
