"""
Message handlers: voice, audio, video_note, document, video, text, catch-all.
"""

from pathlib import Path

from aiogram import Bot, F, Router, types
from aiogram.filters import StateFilter

from application.pipelines import process_audio, process_text, process_youtube
from application.state import active_tasks
from infrastructure.external_api.youtube import wants_diarize
from shared.config import YT_URL_RE, is_allowed, logger
from shared.i18n import t
from shared.utils import audio_suffix, get_audio_from_msg, get_locale_from_message, run_as_cancellable

router = Router(name="messages")


@router.message(F.voice)
async def handle_voice(message: types.Message, bot: Bot):
    """Process Telegram voice messages (.ogg)."""
    from_user = message.from_user
    if not from_user or not is_allowed(from_user.id):
        return
    if not message.voice or not message.voice.file_id:
        return
    await run_as_cancellable(from_user.id, process_audio(message, bot, message.voice.file_id, ".ogg"))


@router.message(F.audio)
async def handle_audio(message: types.Message, bot: Bot):
    """Process audio file attachments (webm, mp3, m4a, etc.)."""
    from_user = message.from_user
    if not from_user or not is_allowed(from_user.id):
        return
    audio = message.audio
    if not audio or not audio.file_id:
        return
    suffix = audio_suffix(audio.mime_type or "", audio.file_name or "")
    await run_as_cancellable(from_user.id, process_audio(message, bot, audio.file_id, suffix))


@router.message(F.video_note)
async def handle_video_note(message: types.Message, bot: Bot):
    """Process video notes (round video messages, typically .mp4)."""
    from_user = message.from_user
    if not from_user or not is_allowed(from_user.id):
        return
    if not message.video_note or not message.video_note.file_id:
        return
    await run_as_cancellable(from_user.id, process_audio(message, bot, message.video_note.file_id, ".mp4"))


@router.message(F.document)
async def handle_document(message: types.Message, bot: Bot):
    """Process document attachments that are audio/video files (webm, mp3, etc.)."""
    locale = await get_locale_from_message(message)
    from_user = message.from_user
    if not from_user or not is_allowed(from_user.id):
        return
    doc = message.document
    if not doc or not doc.file_id:
        return
    mime = doc.mime_type or ""
    if not any(t in mime for t in ("audio", "video", "ogg", "webm", "mp4", "mp3", "m4a", "aac", "flac", "wav")):
        await message.answer(t("messages.unsupported_file", locale))
        return
    suffix = audio_suffix(mime, doc.file_name or "")
    await run_as_cancellable(from_user.id, process_audio(message, bot, doc.file_id, suffix))


@router.message(F.video)
async def handle_video(message: types.Message, bot: Bot):
    """Process video file attachments (mp4, webm, mkv, etc.) — transcribes audio track."""
    from_user = message.from_user
    if not from_user or not is_allowed(from_user.id):
        return
    video = message.video
    if not video or not video.file_id:
        return
    mime = video.mime_type or ""
    if "webm" in mime:
        suffix = ".webm"
    elif "mp4" in mime:
        suffix = ".mp4"
    else:
        suffix = Path(video.file_name or "video").suffix or ".mp4"
    await run_as_cancellable(from_user.id, process_audio(message, bot, video.file_id, suffix))


@router.message(F.text, StateFilter(None))
async def handle_text(message: types.Message, bot: Bot):
    """Process regular text messages through LLM."""
    locale = await get_locale_from_message(message)
    from_user = message.from_user
    if not from_user:
        return
    text = message.text
    if not text:
        return
    logger.info("Text: user_id=%d, len=%d", from_user.id, len(text))
    if not is_allowed(from_user.id):
        return
    if text.startswith("/"):
        logger.debug(
            t("messages.unknown_command", locale),
            from_user.id,
            text.split()[0],
        )
        return

    # Stop command as plain text
    if text.strip().lower() in ("стоп", "stop"):
        user_id = from_user.id
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
            await run_as_cancellable(from_user.id, process_audio(message, bot, file_id, suffix))
            return

    # Check for YouTube URL
    yt_match = YT_URL_RE.search(text)
    if yt_match:
        video_id = yt_match.group(1)
        url = f"https://www.youtube.com/watch?v={video_id}"
        diarize = wants_diarize(text)
        await run_as_cancellable(from_user.id, process_youtube(message, url, diarize))
        return

    await run_as_cancellable(from_user.id, process_text(message))


@router.message(StateFilter(None))
async def handle_unhandled(message: types.Message):
    """Catch-all: log unhandled content types for debugging."""
    logger.warning(
        "Unhandled message: content_type=%s, document mime=%s name=%s",
        message.content_type,
        message.document.mime_type if message.document else None,
        message.document.file_name if message.document else None,
    )
