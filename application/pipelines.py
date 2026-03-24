"""
Processing pipelines for audio, YouTube, and text messages.
"""

import asyncio
import os
import re
import shutil
import tempfile
import time
import uuid
from datetime import datetime

from aiogram import Bot, types
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile

from application.state import (
    FREE_USES_LIMIT,
    can_use_shared_credentials,
    cleanup_yt_cache,
    get_mode,
    get_user_setting,
    increment_free_uses,
    yt_transcripts,
)
from shared.config import ALLOWED_USER_IDS, HF_TOKEN, logger
from infrastructure.external_api.youtube import download_yt_audio, transcribe_diarized
from infrastructure.external_api.groq_client import transcribe
from infrastructure.external_api.llm_client import ask_ollama, format_note_ollama, summarize_ollama
from infrastructure.storage.gdocs import is_gdocs_enabled, save_to_gdocs
from infrastructure.storage.obsidian import is_obsidian_enabled, save_note
from shared.i18n import t
from shared.keyboards import stop_keyboard, yt_summary_keyboard
from shared.utils import escape_md, get_locale_from_message


async def _check_free_tier(message: types.Message, locale: str) -> bool:
    """Check free-tier limit and count usage. Returns False if blocked."""
    user_id = message.from_user.id
    if not can_use_shared_credentials(user_id):
        await message.answer(t("settings.free_tier.limit_reached", locale, limit=FREE_USES_LIMIT))
        return False
    # Count usage only for users subject to the free tier
    if ALLOWED_USER_IDS and user_id not in ALLOWED_USER_IDS and not get_user_setting(user_id, "llm_api_key"):
        new_count = increment_free_uses(user_id)
        remaining = FREE_USES_LIMIT - new_count
        if remaining == 0:
            await message.answer(t("settings.free_tier.last_use", locale))
        elif remaining > 0:
            await message.answer(
                t("settings.free_tier.uses_remaining", locale, remaining=remaining, limit=FREE_USES_LIMIT)
            )
    return True


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
        # 1. Download audio
        audio_path, title, duration = await download_yt_audio(url, locale)
        duration_min = duration // 60
        await processing_msg.edit_text(t("pipelines.youtube.transcribing", locale, title=title, duration=duration_min))

        # 2. Transcribe
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

        # 3. Send transcript as .txt file
        transcript_bytes = transcript_text.encode("utf-8")
        safe_title = re.sub(r"[^\w\s-]", "", title)[:50].strip() or "transcript"
        doc = BufferedInputFile(transcript_bytes, filename=f"{safe_title}.txt")
        await message.answer_document(doc, caption=t("pipelines.youtube.transcript_caption", locale))

        # 4. Save to Google Docs if enabled
        if is_gdocs_enabled(message.from_user.id):
            await save_to_gdocs(message.from_user.id, message.from_user.username, transcript_text)

        # 5. Cache transcript for re-summarization
        cleanup_yt_cache()
        cache_key = uuid.uuid4().hex[:8]
        yt_transcripts[cache_key] = {
            "transcript": transcript_text,
            "title": title,
            "ts": time.time(),
        }

        # 6. Generate brief summary
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
                # Also clean up the temp directory
                parent = os.path.dirname(audio_path)
                if parent and os.path.basename(parent).startswith("tmp"):
                    shutil.rmtree(parent, ignore_errors=True)
            except OSError as e:
                logger.warning("Failed to clean up temp file %s: %s", audio_path, e)


async def process_audio(message: types.Message, bot: Bot, file_id: str, suffix: str):
    """Download audio file → transcribe → (LLM if chat mode) → reply."""
    locale = get_locale_from_message(message)
    user_id = message.from_user.id
    logger.info(
        "Audio: user_id=%d, type=%s, mode=%s, file_id=%s",
        user_id,
        suffix,
        get_mode(user_id),
        file_id[:20],
    )
    if not await _check_free_tier(message, locale):
        return
    processing_msg = await message.answer(t("pipelines.audio.transcribing", locale), reply_markup=stop_keyboard(locale))

    try:
        # 1. Download audio file
        file = await bot.get_file(file_id)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = tmp.name
        await bot.download_file(file.file_path, tmp_path)

        # 2. Transcribe
        try:
            user_text = await transcribe(tmp_path)
        finally:
            os.unlink(tmp_path)

        if not user_text.strip():
            await processing_msg.edit_text(t("pipelines.audio.no_speech", locale), reply_markup=None)
            return

        # 3. Save to Google Docs if enabled
        if is_gdocs_enabled(user_id):
            await save_to_gdocs(user_id, message.from_user.username, user_text)

        # 4. Transcribe-only mode — just return the text
        if get_mode(user_id) == "transcribe":
            await processing_msg.edit_text(user_text, reply_markup=None)
            return

        # 5. Obsidian note mode — format transcription as a structured Markdown note
        if get_mode(user_id) == "note":
            await processing_msg.edit_text(t("pipelines.audio.formatting_note", locale))
            title, tags, body = await format_note_ollama(user_text, locale, user_id=user_id)

            now = datetime.now()
            date_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M")
            all_tags = ["voice-note"] + tags
            tags_yaml = "[" + ", ".join(all_tags) + "]"

            note_md = f"---\ndate: {date_str}\ntime: {time_str}\ntags: {tags_yaml}\n---\n\n# {title}\n\n{body}\n"

            safe_title = re.sub(r"[^\w\s-]", "", title)[:40].strip() or "note"
            filename = f"{date_str}-{safe_title.replace(' ', '-')}.md"

            vault_saved = False
            disk_url = None
            if is_obsidian_enabled(user_id):
                try:
                    location, disk_url = await save_note(filename, note_md, user_id=user_id)
                    vault_saved = True
                    # Add disk URL to the note if saved via OAuth
                    if disk_url:
                        note_md = f"{note_md}\n\n🔗 [View on Yandex.Disk]({disk_url})"
                        # Re-save with updated content
                        await save_note(filename, note_md, user_id=user_id)
                except Exception as e:
                    logger.error("Failed to save note to Obsidian vault: %s", e)

            doc = BufferedInputFile(note_md.encode("utf-8"), filename=filename)

            tag_line = " ".join(f"#{tag}" for tag in all_tags)
            vault_line = t("pipelines.audio.vault_saved", locale) if vault_saved else ""
            if disk_url:
                vault_line = t("pipelines.audio.vault_saved_with_url", locale, disk_url=disk_url)
            caption = t("pipelines.audio.note_caption", locale, title=title, tags=tag_line, vault_line=vault_line)
            await processing_msg.delete()
            await message.answer_document(doc, caption=caption)
            return

        # Chat mode — send to LLM
        await processing_msg.edit_text(
            t("pipelines.audio.recognized_header", locale)
            + f"_{escape_md(user_text)}_"
            + "\n\n"
            + t("pipelines.audio.thinking", locale),
            parse_mode=ParseMode.MARKDOWN,
        )

        response = await ask_ollama(user_id, user_text, locale)

        full_text = (
            t("pipelines.audio.recognized_header", locale)
            + f"_{escape_md(user_text)}_"
            + "\n\n"
            + t("pipelines.audio.response_header", locale)
            + response
        )
        if len(full_text) > 4000:
            await processing_msg.edit_text(
                t("pipelines.audio.recognized_header", locale) + f"_{escape_md(user_text)}_",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=None,
            )
            for i in range(0, len(response), 4000):
                await message.answer(response[i : i + 4000])
        else:
            await processing_msg.edit_text(full_text, parse_mode=ParseMode.MARKDOWN, reply_markup=None)

    except asyncio.CancelledError:
        try:
            await processing_msg.edit_text(t("pipelines.audio.stopped", locale), reply_markup=None)
        except Exception:
            pass
        raise
    except Exception as e:
        if "file is too big" in str(e).lower():
            logger.warning("Audio file too big: user_id=%d, file_id=%s", message.from_user.id, file_id[:20])
            await processing_msg.edit_text(t("pipelines.audio.file_too_big", locale), reply_markup=None)
        else:
            logger.exception("Audio processing error: user_id=%d", message.from_user.id)
            await processing_msg.edit_text(
                t("pipelines.audio.processing_error", locale, error=str(e)), reply_markup=None
            )


async def process_text(message: types.Message):
    """Send text message to LLM and reply."""
    locale = get_locale_from_message(message)
    user_id = message.from_user.id
    if not await _check_free_tier(message, locale):
        return
    processing_msg = await message.answer(t("pipelines.text.thinking", locale), reply_markup=stop_keyboard(locale))
    try:
        response = await ask_ollama(user_id, message.text, locale)

        if len(response) > 4000:
            await processing_msg.delete()
            for i in range(0, len(response), 4000):
                await message.answer(response[i : i + 4000])
        else:
            await processing_msg.edit_text(response, reply_markup=None)

    except asyncio.CancelledError:
        try:
            await processing_msg.edit_text(t("pipelines.text.stopped", locale), reply_markup=None)
        except Exception:
            pass
        raise
    except Exception as e:
        logger.exception("Text processing error")
        await processing_msg.edit_text(t("pipelines.text.error", locale, error=str(e)), reply_markup=None)
