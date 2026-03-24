"""
In-memory state: conversation history, user modes, YouTube transcript cache,
per-user settings with disk persistence.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path

from config import ALLOWED_USER_IDS, DEFAULT_LANGUAGE, MAX_HISTORY, YT_CACHE_TTL

_log = logging.getLogger(__name__)

# ── Persistence ───────────────────────────────────────────────────────────────

_SETTINGS_FILE = Path(__file__).parent / "data" / "user_settings.json"

FREE_USES_LIMIT = 3

# Per-user settings (persisted to disk)
user_settings: dict[int, dict] = {}

# Per-user free-use counters (persisted alongside user_settings)
user_free_uses: dict[int, int] = {}


def get_user_setting(user_id: int, key: str, default=None):
    return user_settings.get(user_id, {}).get(key, default)


def set_user_setting(user_id: int, key: str, value: str) -> None:
    if user_id not in user_settings:
        user_settings[user_id] = {}
    user_settings[user_id][key] = value
    save_user_settings()


def clear_user_setting(user_id: int, key: str) -> None:
    if user_id in user_settings and key in user_settings[user_id]:
        del user_settings[user_id][key]
        save_user_settings()


def clear_user_settings_section(user_id: int, keys: list[str]) -> None:
    if user_id not in user_settings:
        return
    for key in keys:
        user_settings[user_id].pop(key, None)
    save_user_settings()


def save_user_settings() -> None:
    _SETTINGS_FILE.parent.mkdir(exist_ok=True)
    data = {
        "settings": {str(uid): v for uid, v in user_settings.items()},
        "free_uses": {str(uid): v for uid, v in user_free_uses.items()},
    }
    tmp = _SETTINGS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_SETTINGS_FILE)
    os.chmod(_SETTINGS_FILE, 0o600)


def load_user_settings() -> None:
    if not _SETTINGS_FILE.exists():
        return
    try:
        data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
        for uid_str, v in data.get("settings", {}).items():
            user_settings[int(uid_str)] = v
        for uid_str, count in data.get("free_uses", {}).items():
            user_free_uses[int(uid_str)] = count
        _log.info("Loaded user settings for %d users", len(user_settings))
    except Exception as e:
        _log.error("Failed to load user settings: %s", e)


# ── Free-tier ─────────────────────────────────────────────────────────────────


def get_free_uses(user_id: int) -> int:
    return user_free_uses.get(user_id, 0)


def increment_free_uses(user_id: int) -> int:
    """Increment and persist the free-use counter. Returns the new count."""
    user_free_uses[user_id] = user_free_uses.get(user_id, 0) + 1
    save_user_settings()
    return user_free_uses[user_id]


def has_free_uses_left(user_id: int) -> bool:
    return get_free_uses(user_id) < FREE_USES_LIMIT


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
    return has_free_uses_left(user_id)


# Per-user conversation history
conversations: dict[int, list[dict]] = {}

# Per-user mode: "chat" (transcribe + LLM) or "transcribe" (transcribe only)
user_modes: dict[int, str] = {}

# Per-user Google Docs saving toggle (opt-in, default off)
user_gdocs: dict[int, bool] = {}

# Per-user language preference (default from config)
user_languages: dict[int, str] = {}

# YouTube transcript cache for inline button re-summarization
# Key: 8-char hex ID, Value: {"transcript": str, "title": str, "ts": float}
yt_transcripts: dict[str, dict] = {}

# Per-user active processing task (for cancellation via /stop)
active_tasks: dict[int, asyncio.Task] = {}

# Cached Groq rate-limit headers from the last successful transcription response
groq_limits: dict[str, str | None] = {}


def update_groq_limits(headers) -> None:
    """Extract and cache x-ratelimit-* headers from a Groq API response."""
    groq_limits.update(
        {
            "limit_req": headers.get("x-ratelimit-limit-requests"),
            "remaining_req": headers.get("x-ratelimit-remaining-requests"),
            "reset_req": headers.get("x-ratelimit-reset-requests"),
            "limit_tokens": headers.get("x-ratelimit-limit-tokens"),
            "remaining_tokens": headers.get("x-ratelimit-remaining-tokens"),
            "reset_tokens": headers.get("x-ratelimit-reset-tokens"),
        }
    )


def get_history(user_id: int) -> list[dict]:
    if user_id not in conversations:
        conversations[user_id] = []
    return conversations[user_id]


def add_to_history(user_id: int, role: str, content: str):
    history = get_history(user_id)
    history.append({"role": role, "content": content})
    # Trim: keep last MAX_HISTORY message pairs
    if len(history) > MAX_HISTORY * 2:
        conversations[user_id] = history[-(MAX_HISTORY * 2) :]


def clear_history(user_id: int):
    conversations[user_id] = []


def get_language(user_id: int) -> str:
    """Get user's language preference, default to config value."""
    return user_languages.get(user_id, DEFAULT_LANGUAGE)


def set_language(user_id: int, lang: str):
    """Set user's language preference."""
    user_languages[user_id] = lang


def get_mode(user_id: int) -> str:
    return user_modes.get(user_id, "chat")


def cleanup_yt_cache():
    """Remove expired entries from yt_transcripts."""
    now = time.time()
    expired = [k for k, v in yt_transcripts.items() if now - v["ts"] > YT_CACHE_TTL]
    for k in expired:
        del yt_transcripts[k]
