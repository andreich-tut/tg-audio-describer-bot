"""
Message handlers: voice, audio, video_note, document, video, text, catch-all.
"""

from pathlib import Path

from aiogram import Bot, F, Router, types
from aiogram.filters import StateFilter

from application.state import active_tasks
from application.pipelines import process_audio, process_text, process_youtube
from infrastructure.external_api.youtube import wants_diarize
from shared.config import YT_URL_RE, is_allowed, logger
from shared.i18n import get_user_locale, t
from shared.utils import audio_suffix, get_audio_from_msg, get_locale_from_message, run_as_cancellable

router = Router(name="messages")


@router.message(F.voice)
async def handle_voice(message: types.Message, bot: Bot):
    """Process Telegram voice messages (.ogg)."""
    if not is_allowed(message.from_user.id):
        return
    await run_as_cancellable(message.from_user.id, process_audio(message, bot, message.voice.file_id, ".ogg"))


@router.message(F.audio)
async def handle_audio(message: types.Message, bot: Bot):
    """Process audio file attachments (webm, mp3, m4a, etc.)."""
    if not is_allowed(message.from_user.id):
        return
    suffix = audio_suffix(message.audio.mime_type, message.audio.file_name)
    await run_as_cancellable(message.from_user.id, process_audio(message, bot, message.audio.file_id, suffix))


@router.message(F.video_note)
async def handle_video_note(message: types.Message, bot: Bot):
    """Process video notes (round video messages, typically .mp4)."""
    if not is_allowed(message.from_user.id):
        return
    await run_as_cancellable(message.from_user.id, process_audio(message, bot, message.video_note.file_id, ".mp4"))


@router.message(F.document)
async def handle_document(message: types.Message, bot: Bot):
    """Process document attachments that are audio/video files (webm, mp3, etc.)."""
    locale = get_user_locale(message.from_user.id)
    if not is_allowed(message.from_user.id):
        return
    mime = message.document.mime_type or ""
    if not any(t in mime for t in ("audio", "video", "ogg", "webm", "mp4", "mp3", "m4a", "aac", "flac", "wav")):
        await message.answer(t("messages.unsupported_file", locale))
        return
    suffix = audio_suffix(mime, message.document.file_name)
    await run_as_cancellable(message.from_user.id, process_audio(message, bot, message.document.file_id, suffix))


@router.message(F.video)
async def handle_video(message: types.Message, bot: Bot):
    """Process video file attachments (mp4, webm, mkv, etc.) — transcribes audio track."""
    if not is_allowed(message.from_user.id):
        return
    mime = message.video.mime_type or ""
    if "webm" in mime:
        suffix = ".webm"
    elif "mp4" in mime:
        suffix = ".mp4"
    else:
        suffix = Path(message.video.file_name or "video").suffix or ".mp4"
    await run_as_cancellable(message.from_user.id, process_audio(message, bot, message.video.file_id, suffix))


@router.message(F.text, StateFilter(None))
async def handle_text(message: types.Message, bot: Bot):
    """Process regular text messages through LLM."""
    locale = get_locale_from_message(message)
    logger.info("Text: user_id=%d, len=%d", message.from_user.id, len(message.text))
    if not is_allowed(message.from_user.id):
        return
    if message.text.startswith("/"):
        logger.debug(
            t("messages.unknown_command", locale),
            message.from_user.id,
            message.text.split()[0],
        )
        return

    # Stop command as plain text
    if message.text.strip().lower() in ("стоп", "stop"):
        user_id = message.from_user.id
        task = active_tasks.get(user_id)
        if task and not task.done():
            task.cancel()
            logger.info("Task cancelled via text stop: user_id=%d", user_id)
        else:
            await message.answer(t("messages.no_active_tasks", locale))
        return

    # If replying to a message with audio — process that audio
    if message.reply_to_message:
        audio = get_audio_from_msg(message.reply_to_message)
        if audio:
            file_id, suffix = audio
            await run_as_cancellable(message.from_user.id, process_audio(message, bot, file_id, suffix))
            return

    # Check for YouTube URL
    yt_match = YT_URL_RE.search(message.text)
    if yt_match:
        video_id = yt_match.group(1)
        url = f"https://www.youtube.com/watch?v={video_id}"
        diarize = wants_diarize(message.text)
        await run_as_cancellable(message.from_user.id, process_youtube(message, url, diarize))
        return

    await run_as_cancellable(message.from_user.id, process_text(message))


@router.message(StateFilter(None))
async def handle_unhandled(message: types.Message):
    """Catch-all: log unhandled content types for debugging."""
    logger.warning(
        "Unhandled message: content_type=%s, document mime=%s name=%s",
        message.content_type,
        message.document.mime_type if message.document else None,
        message.document.file_name if message.document else None,
    )
