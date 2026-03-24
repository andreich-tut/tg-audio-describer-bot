"""
Obsidian vault integration: save Markdown notes to a local vault folder
or directly to Yandex.Disk via WebDAV (OAuth authentication).

Priority (per user, falling back to global config):
  1. Yandex.Disk WebDAV — if OAuth token is set
  2. Local filesystem   — if obsidian_vault_path is set
"""

import logging
from datetime import datetime
from pathlib import Path

import httpx

from config import (
    OBSIDIAN_INBOX_FOLDER,
    OBSIDIAN_VAULT_PATH,
    YANDEX_DISK_PATH,
)
from infrastructure.external_api.yandex_client import refresh_access_token
from state import get_user_setting, get_user_setting_json

logger = logging.getLogger(__name__)

_WEBDAV_BASE = "https://webdav.yandex.ru"


def _get_cfg(user_id: int) -> dict:
    """Resolve effective Obsidian/Yandex.Disk config for a user."""
    oauth_token = get_user_setting_json(user_id, "yandex_oauth_token")
    return {
        "yadisk_path": get_user_setting(user_id, "yadisk_path") or YANDEX_DISK_PATH,
        "vault_path": get_user_setting(user_id, "obsidian_vault_path") or OBSIDIAN_VAULT_PATH,
        "inbox_folder": get_user_setting(user_id, "obsidian_inbox_folder") or OBSIDIAN_INBOX_FOLDER,
        "oauth_token": oauth_token,
    }


def is_obsidian_enabled(user_id: int = 0) -> bool:
    cfg = _get_cfg(user_id)
    # OAuth token takes priority
    if cfg["oauth_token"] and cfg["oauth_token"].get("access_token"):
        return True
    if not cfg["vault_path"]:
        return False
    vault = Path(cfg["vault_path"])
    if not vault.is_dir():
        logger.warning("obsidian_vault_path is set but directory does not exist: %s", vault)
        return False
    return True


async def save_note(filename: str, content: str, user_id: int = 0) -> tuple[str, str | None]:
    """Write a Markdown note to the configured destination.

    Returns tuple of (location, disk_url) where disk_url is None for local saves.
    Raises on failure.
    """
    cfg = _get_cfg(user_id)
    if cfg["oauth_token"] and cfg["oauth_token"].get("access_token"):
        return await _save_webdav_oauth(filename, content, cfg, user_id)
    location = _save_local(filename, content, cfg)
    return location, None


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


# ── Yandex.Disk WebDAV (OAuth) ───────────────────────────────────────────────


async def _save_webdav_oauth(filename: str, content: str, cfg: dict, user_id: int) -> tuple[str, str]:
    """Save note to Yandex.Disk using OAuth token authentication.

    Returns tuple of (location, disk_url).
    """
    from state import set_user_setting_json

    oauth_token = cfg["oauth_token"]

    # Refresh token if expired
    if oauth_token.get("refresh_token") and (
        not oauth_token.get("expires_at") or datetime.fromisoformat(oauth_token["expires_at"]) <= datetime.now()
    ):
        new_token = await refresh_access_token(oauth_token["refresh_token"])
        if new_token:
            new_token_dict = new_token.to_dict()
            new_token_dict["login"] = oauth_token.get("login")
            set_user_setting_json(user_id, "yandex_oauth_token", new_token_dict)
            oauth_token = new_token_dict

    access_token = oauth_token["access_token"]
    folder_parts = [cfg["yadisk_path"].strip("/")]
    if cfg["inbox_folder"]:
        folder_parts.append(cfg["inbox_folder"].strip("/"))
    folder_path = "/".join(folder_parts)

    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
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

    # Generate Yandex.Disk URL for the saved note
    disk_url = f"https://disk.yandex.ru/client/files/{folder_path.replace('/', '%2F')}/{filename.replace(' ', '%20')}"
    location = f"Yandex.Disk:/{file_path}"

    logger.info("Obsidian note saved to %s (OAuth)", location)
    return location, disk_url
