"""
Helper utilities for the bot.
"""

import asyncio
from pathlib import Path

from aiogram import types
from aiogram.types import CallbackQuery, Message

from shared.i18n import get_user_locale
from application.state import active_tasks


def audio_suffix(mime: str, filename: str | None, fallback: str = ".audio") -> str:
    """Infer file suffix from MIME type."""
    mime = mime or ""
    if "webm" in mime:
        return ".webm"
    if "m4a" in mime or "aac" in mime:
        return ".m4a"
    if "mp4" in mime:
        return ".m4a"
    if "mpeg" in mime or "mp3" in mime:
        return ".mp3"
    if "ogg" in mime:
        return ".ogg"
    if "flac" in mime:
        return ".flac"
    if "wav" in mime:
        return ".wav"
    return Path(filename or "file").suffix or fallback


def escape_md(text: str) -> str:
    """Escape Telegram Markdown v1 special characters in plain text."""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, "\\" + ch)
    return text


async def run_as_cancellable(user_id: int, coro) -> None:
    """Run coroutine as a cancellable task, registered in active_tasks."""
    task = asyncio.create_task(coro)
    active_tasks[user_id] = task
    try:
        await task
    except asyncio.CancelledError:
        pass
    finally:
        active_tasks.pop(user_id, None)


def get_audio_from_msg(msg: types.Message) -> tuple[str, str] | None:
    """Return (file_id, suffix) if msg contains audio/voice/video, else None."""
    if msg.voice:
        return msg.voice.file_id, ".ogg"
    if msg.audio:
        return msg.audio.file_id, audio_suffix(msg.audio.mime_type, msg.audio.file_name)
    if msg.video_note:
        return msg.video_note.file_id, ".mp4"
    if msg.video:
        mime = msg.video.mime_type or ""
        suffix = (
            ".webm"
            if "webm" in mime
            else ".mp4"
            if "mp4" in mime
            else (Path(msg.video.file_name or "video").suffix or ".mp4")
        )
        return msg.video.file_id, suffix
    if msg.document:
        mime = msg.document.mime_type or ""
        if any(t in mime for t in ("audio", "video", "ogg", "webm", "mp4", "mp3", "m4a", "aac", "flac", "wav")):
            return msg.document.file_id, audio_suffix(mime, msg.document.file_name)
    return None


def get_locale_from_message(message: Message) -> str:
    """Get locale from a Telegram message."""
    return get_user_locale(message.from_user.id, message.from_user.language_code)


def get_locale_from_callback(callback: CallbackQuery) -> str:
    """Get locale from a Telegram callback query."""
    return get_user_locale(callback.from_user.id, callback.from_user.language_code)
