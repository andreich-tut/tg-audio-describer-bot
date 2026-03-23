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

from config import HF_TOKEN, logger
from core.helpers import escape_md
from core.keyboards import stop_keyboard, yt_summary_keyboard
from services.gdocs import is_gdocs_enabled, save_to_gdocs
from services.llm import ask_ollama, format_note_ollama, summarize_ollama
from services.obsidian import is_obsidian_enabled, save_note
from services.stt import transcribe
from services.youtube import download_yt_audio, transcribe_diarized
from state import cleanup_yt_cache, get_mode, yt_transcripts


async def process_youtube(message: types.Message, url: str, diarize: bool):
    """Download YouTube audio, transcribe, send transcript file, summarize with inline buttons."""
    logger.info("YouTube: user_id=%d, url=%s, diarize=%s", message.from_user.id, url, diarize)
    processing_msg = await message.answer("📥 Загружаю аудио с YouTube...", reply_markup=stop_keyboard())
    audio_path = None

    try:
        # 1. Download audio
        audio_path, title, duration = await download_yt_audio(url)
        duration_min = duration // 60
        await processing_msg.edit_text(f"🎙 Расшифровываю: {title} ({duration_min} мин)...")

        # 2. Transcribe
        if diarize:
            if not HF_TOKEN:
                await processing_msg.edit_text(
                    "⚠️ Для распознавания спикеров нужен HF_TOKEN в .env. Расшифровываю без спикеров..."
                )
                transcript_text = await transcribe(audio_path)
            else:
                await processing_msg.edit_text(f"🎙 Расшифровываю со спикерами: {title} ({duration_min} мин)...")
                transcript_text = await transcribe_diarized(audio_path)
        else:
            transcript_text = await transcribe(audio_path)

        if not transcript_text.strip():
            await processing_msg.edit_text("🤷 Не удалось распознать речь в видео.", reply_markup=None)
            return

        # 3. Send transcript as .txt file
        transcript_bytes = transcript_text.encode("utf-8")
        safe_title = re.sub(r"[^\w\s-]", "", title)[:50].strip() or "transcript"
        doc = BufferedInputFile(transcript_bytes, filename=f"{safe_title}.txt")
        await message.answer_document(doc, caption="📄 Полная расшифровка")

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
        await processing_msg.edit_text("🤖 Генерирую саммари...")
        summary = await summarize_ollama(transcript_text, "brief", title)

        header = "📋 *Саммари:*\n\n"
        full_msg = header + summary
        if len(full_msg) > 4000:
            await processing_msg.edit_text(header, parse_mode=ParseMode.MARKDOWN, reply_markup=None)
            for i in range(0, len(summary), 4000):
                await message.answer(summary[i : i + 4000])
            await message.answer(
                "Выберите формат саммари:",
                reply_markup=yt_summary_keyboard(cache_key),
            )
        else:
            await processing_msg.edit_text(
                full_msg,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=yt_summary_keyboard(cache_key),
            )

    except asyncio.CancelledError:
        try:
            await processing_msg.edit_text("🛑 Остановлено.", reply_markup=None)
        except Exception:
            pass
        raise
    except ValueError as e:
        logger.warning("YouTube validation error: user_id=%d, %s", message.from_user.id, e)
        await processing_msg.edit_text(f"❌ {e}", reply_markup=None)
    except Exception as e:
        logger.exception("YouTube processing error: user_id=%d", message.from_user.id)
        await processing_msg.edit_text(f"❌ Ошибка: {e}", reply_markup=None)
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
    logger.info(
        "Audio: user_id=%d, type=%s, mode=%s, file_id=%s",
        message.from_user.id,
        suffix,
        get_mode(message.from_user.id),
        file_id[:20],
    )
    processing_msg = await message.answer("🎙 Распознаю голос...", reply_markup=stop_keyboard())

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
            await processing_msg.edit_text("🤷 Не удалось распознать речь. Попробуй ещё раз.", reply_markup=None)
            return

        # 3. Save to Google Docs if enabled
        if is_gdocs_enabled(message.from_user.id):
            await save_to_gdocs(message.from_user.id, message.from_user.username, user_text)

        # 4. Transcribe-only mode — just return the text
        if get_mode(message.from_user.id) == "transcribe":
            await processing_msg.edit_text(user_text, reply_markup=None)
            return

        # 5. Obsidian note mode — format transcription as a structured Markdown note
        if get_mode(message.from_user.id) == "note":
            await processing_msg.edit_text("📓 Оформляю заметку...")
            title, tags, body = await format_note_ollama(user_text)

            now = datetime.now()
            date_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M")
            all_tags = ["voice-note"] + tags
            tags_yaml = "[" + ", ".join(all_tags) + "]"

            note_md = f"---\ndate: {date_str}\ntime: {time_str}\ntags: {tags_yaml}\n---\n\n# {title}\n\n{body}\n"

            safe_title = re.sub(r"[^\w\s-]", "", title)[:40].strip() or "note"
            filename = f"{date_str}-{safe_title.replace(' ', '-')}.md"

            vault_saved = False
            if is_obsidian_enabled():
                try:
                    await save_note(filename, note_md)
                    vault_saved = True
                except Exception as e:
                    logger.error("Failed to save note to Obsidian vault: %s", e)

            doc = BufferedInputFile(note_md.encode("utf-8"), filename=filename)

            tag_line = " ".join(f"#{t}" for t in all_tags)
            vault_line = "\n📁 Сохранено в vault" if vault_saved else ""
            caption = f"📓 {title}\n{tag_line}{vault_line}"
            await processing_msg.delete()
            await message.answer_document(doc, caption=caption)
            return

        # Chat mode — send to LLM
        await processing_msg.edit_text(f"📝 _{escape_md(user_text)}_\n\n⏳ Думаю...", parse_mode=ParseMode.MARKDOWN)

        response = await ask_ollama(message.from_user.id, user_text)

        full_text = f"📝 *Распознано:*\n_{escape_md(user_text)}_\n\n🤖 *Ответ:*\n{response}"
        if len(full_text) > 4000:
            await processing_msg.edit_text(
                f"📝 _{escape_md(user_text)}_", parse_mode=ParseMode.MARKDOWN, reply_markup=None
            )
            for i in range(0, len(response), 4000):
                await message.answer(response[i : i + 4000])
        else:
            await processing_msg.edit_text(full_text, parse_mode=ParseMode.MARKDOWN, reply_markup=None)

    except asyncio.CancelledError:
        try:
            await processing_msg.edit_text("🛑 Остановлено.", reply_markup=None)
        except Exception:
            pass
        raise
    except Exception as e:
        if "file is too big" in str(e).lower():
            logger.warning("Audio file too big: user_id=%d, file_id=%s", message.from_user.id, file_id[:20])
            await processing_msg.edit_text(
                "❌ Файл слишком большой. Telegram Bot API ограничивает загрузку файлов до 20 МБ.", reply_markup=None
            )
        else:
            logger.exception("Audio processing error: user_id=%d", message.from_user.id)
            await processing_msg.edit_text(f"❌ Ошибка: {e}", reply_markup=None)


async def process_text(message: types.Message):
    """Send text message to LLM and reply."""
    processing_msg = await message.answer("⏳ Думаю...", reply_markup=stop_keyboard())
    try:
        response = await ask_ollama(message.from_user.id, message.text)

        if len(response) > 4000:
            await processing_msg.delete()
            for i in range(0, len(response), 4000):
                await message.answer(response[i : i + 4000])
        else:
            await processing_msg.edit_text(response, reply_markup=None)

    except asyncio.CancelledError:
        try:
            await processing_msg.edit_text("🛑 Остановлено.", reply_markup=None)
        except Exception:
            pass
        raise
    except Exception as e:
        logger.exception("Text processing error")
        await processing_msg.edit_text(f"❌ Ошибка: {e}", reply_markup=None)
