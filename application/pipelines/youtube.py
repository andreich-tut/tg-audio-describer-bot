"""
YouTube processing pipeline.
"""

import asyncio
import os
import re
import shutil
import time
import uuid

from aiogram import types
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile

from application.pipelines.audio import _check_free_tier
from application.state import cleanup_yt_cache, yt_transcripts
from infrastructure.external_api.groq_client import transcribe
from infrastructure.external_api.llm_client import summarize_ollama
from infrastructure.external_api.youtube import download_yt_audio, transcribe_diarized
from infrastructure.storage.gdocs import is_gdocs_enabled, save_to_gdocs
from shared.config import HF_TOKEN, logger
from shared.i18n import t
from shared.keyboards import stop_keyboard, yt_summary_keyboard
from shared.utils import get_locale_from_message


async def process_youtube(message: types.Message, url: str, diarize: bool):
    """Download YouTube audio, transcribe, send transcript file, summarize with inline buttons."""
    locale = get_locale_from_message(message)
    user_id = message.from_user.id
    logger.info("YouTube: user_id=%d, url=%s, diarize=%s", user_id, url, diarize)
    if not await _check_free_tier(message, locale):
        return
    processing_msg = await message.answer(
        t("pipelines.youtube.downloading", locale), reply_markup=stop_keyboard(locale)
    )
    audio_path = None

    try:
        audio_path, title, duration = await download_yt_audio(url, locale)
        duration_min = duration // 60
        await processing_msg.edit_text(t("pipelines.youtube.transcribing", locale, title=title, duration=duration_min))

        if diarize:
            if not HF_TOKEN:
                await processing_msg.edit_text(t("pipelines.youtube.speakers_need_token", locale))
                transcript_text = await transcribe(audio_path)
            else:
                await processing_msg.edit_text(
                    t("pipelines.youtube.transcribing_with_speakers", locale, title=title, duration=duration_min)
                )
                transcript_text = await transcribe_diarized(audio_path)
        else:
            transcript_text = await transcribe(audio_path)

        if not transcript_text.strip():
            await processing_msg.edit_text(t("pipelines.youtube.no_speech", locale), reply_markup=None)
            return

        transcript_bytes = transcript_text.encode("utf-8")
        safe_title = re.sub(r"[^\w\s-]", "", title)[:50].strip() or "transcript"
        doc = BufferedInputFile(transcript_bytes, filename=f"{safe_title}.txt")
        await message.answer_document(doc, caption=t("pipelines.youtube.transcript_caption", locale))

        if is_gdocs_enabled(message.from_user.id):
            await save_to_gdocs(message.from_user.id, message.from_user.username, transcript_text)

        cleanup_yt_cache()
        cache_key = uuid.uuid4().hex[:8]
        yt_transcripts[cache_key] = {
            "transcript": transcript_text,
            "title": title,
            "ts": time.time(),
        }

        await processing_msg.edit_text(t("pipelines.youtube.generating_summary", locale))
        summary = await summarize_ollama(transcript_text, "brief", title, locale, user_id=user_id)

        header = t("pipelines.youtube.summary_header", locale)
        full_msg = header + summary
        if len(full_msg) > 4000:
            await processing_msg.edit_text(header, parse_mode=ParseMode.MARKDOWN, reply_markup=None)
            for i in range(0, len(summary), 4000):
                await message.answer(summary[i : i + 4000])
            await message.answer(
                t("pipelines.youtube.select_format", locale),
                reply_markup=yt_summary_keyboard(cache_key, locale),
            )
        else:
            await processing_msg.edit_text(
                full_msg,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=yt_summary_keyboard(cache_key, locale),
            )

    except asyncio.CancelledError:
        try:
            await processing_msg.edit_text(t("pipelines.youtube.stopped", locale), reply_markup=None)
        except Exception:
            pass
        raise
    except ValueError as e:
        logger.warning("YouTube validation error: user_id=%d, %s", message.from_user.id, e)
        await processing_msg.edit_text(t("pipelines.youtube.validation_error", locale, error=str(e)), reply_markup=None)
    except Exception as e:
        logger.exception("YouTube processing error: user_id=%d", message.from_user.id)
        await processing_msg.edit_text(t("pipelines.youtube.processing_error", locale, error=str(e)), reply_markup=None)
    finally:
        if audio_path:
            try:
                os.unlink(audio_path)
                parent = os.path.dirname(audio_path)
                if parent and os.path.basename(parent).startswith("tmp"):
                    shutil.rmtree(parent, ignore_errors=True)
            except OSError as e:
                logger.warning("Failed to clean up temp file %s: %s", audio_path, e)
