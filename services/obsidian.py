"""
Obsidian vault integration: save Markdown notes to a local vault folder
or directly to Yandex.Disk via WebDAV.

Priority (per user, falling back to global config):
  1. Yandex.Disk WebDAV — if yadisk_login is set (user or global)
  2. Local filesystem   — if obsidian_vault_path is set (user or global)
"""

import logging
from datetime import datetime
from pathlib import Path

import httpx

from config import (
    OBSIDIAN_INBOX_FOLDER,
    OBSIDIAN_VAULT_PATH,
    YANDEX_DISK_LOGIN,
    YANDEX_DISK_PASSWORD,
    YANDEX_DISK_PATH,
)
from state import get_user_setting

logger = logging.getLogger(__name__)

_WEBDAV_BASE = "https://webdav.yandex.ru"


def _get_cfg(user_id: int) -> dict:
    """Resolve effective Obsidian/Yandex.Disk config for a user."""
    return {
        "yadisk_login": get_user_setting(user_id, "yadisk_login") or YANDEX_DISK_LOGIN,
        "yadisk_password": get_user_setting(user_id, "yadisk_password") or YANDEX_DISK_PASSWORD,
        "yadisk_path": get_user_setting(user_id, "yadisk_path") or YANDEX_DISK_PATH,
        "vault_path": get_user_setting(user_id, "obsidian_vault_path") or OBSIDIAN_VAULT_PATH,
        "inbox_folder": get_user_setting(user_id, "obsidian_inbox_folder") or OBSIDIAN_INBOX_FOLDER,
    }


def is_obsidian_enabled(user_id: int = 0) -> bool:
    cfg = _get_cfg(user_id)
    if cfg["yadisk_login"]:
        return True
    if not cfg["vault_path"]:
        return False
    vault = Path(cfg["vault_path"])
    if not vault.is_dir():
        logger.warning("obsidian_vault_path is set but directory does not exist: %s", vault)
        return False
    return True


async def save_note(filename: str, content: str, user_id: int = 0) -> str:
    """Write a Markdown note to the configured destination.

    Returns a human-readable location string.
    Raises on failure.
    """
    cfg = _get_cfg(user_id)
    if cfg["yadisk_login"]:
        return await _save_webdav(filename, content, cfg)
    return _save_local(filename, content, cfg)


# ── local ────────────────────────────────────────────────────────────────────


def _save_local(filename: str, content: str, cfg: dict) -> str:
    vault = Path(cfg["vault_path"])
    folder = vault / cfg["inbox_folder"] if cfg["inbox_folder"] else vault
    folder.mkdir(parents=True, exist_ok=True)

    dest = folder / filename
    if dest.exists():
        stem, suffix = dest.stem, dest.suffix
        ts = datetime.now().strftime("%H%M%S")
        dest = folder / f"{stem}-{ts}{suffix}"

    dest.write_text(content, encoding="utf-8")
    logger.info("Obsidian note saved locally: %s", dest)
    return str(dest)


# ── Yandex.Disk WebDAV ───────────────────────────────────────────────────────


async def _save_webdav(filename: str, content: str, cfg: dict) -> str:
    auth = (cfg["yadisk_login"], cfg["yadisk_password"])
    folder_parts = [cfg["yadisk_path"].strip("/")]
    if cfg["inbox_folder"]:
        folder_parts.append(cfg["inbox_folder"].strip("/"))
    folder_path = "/".join(folder_parts)

    async with httpx.AsyncClient(auth=auth, timeout=30) as client:
        # Ensure each folder level exists (MKCOL is idempotent — 405 = already exists)
        parts = folder_path.split("/")
        for i in range(1, len(parts) + 1):
            partial = "/".join(parts[:i])
            resp = await client.request("MKCOL", f"{_WEBDAV_BASE}/{partial}")
            if resp.status_code not in (201, 405):
                resp.raise_for_status()

        # Check if file exists and add timestamp suffix if so
        file_path = f"{folder_path}/{filename}"
        head = await client.head(f"{_WEBDAV_BASE}/{file_path}")
        if head.status_code == 200:
            stem = filename.rsplit(".", 1)[0]
            suffix = f".{filename.rsplit('.', 1)[1]}" if "." in filename else ""
            ts = datetime.now().strftime("%H%M%S")
            file_path = f"{folder_path}/{stem}-{ts}{suffix}"

        resp = await client.put(
            f"{_WEBDAV_BASE}/{file_path}",
            content=content.encode("utf-8"),
            headers={"Content-Type": "text/markdown; charset=utf-8"},
        )
        resp.raise_for_status()

    location = f"Yandex.Disk:/{file_path}"
    logger.info("Obsidian note saved to %s", location)
    return location
