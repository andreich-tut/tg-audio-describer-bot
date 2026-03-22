"""
Telegram Voice → LLM Bot
Stack: aiogram 3 + faster-whisper (local GPU) + Ollama

Send a voice message → bot transcribes via Whisper →
sends text to Ollama → returns the response.
Also works with regular text messages.
"""

import asyncio
import os
import re
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, types, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BufferedInputFile, BotCommand

from config import (
    BOT_TOKEN, TOR_PROXY, LLM_MODEL, WHISPER_MODEL, WHISPER_DEVICE,
    ALLOWED_USER_IDS, GDOCS_DOCUMENT_ID, YT_URL_RE, HF_TOKEN,
    is_allowed, logger,
)
from state import (
    get_history, clear_history, get_mode, user_modes, user_gdocs,
    yt_transcripts, cleanup_yt_cache, active_tasks,
)
from services.stt import transcribe
from services.llm import ask_ollama, summarize_ollama, format_note_ollama, ping_llm
from services.youtube import download_yt_audio, wants_diarize, transcribe_diarized
from services.gdocs import gdocs_service, is_gdocs_enabled, save_to_gdocs
from services.obsidian import is_obsidian_enabled, save_note
from services.limits import check_openouter, check_groq, format_limits_message

# ──────────────────────────────────────────────
# Telegram Bot
# ──────────────────────────────────────────────
bot = Bot(token=BOT_TOKEN, session=AiohttpSession(proxy=TOR_PROXY) if TOR_PROXY else None)
dp = Dispatcher()


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def _audio_suffix(mime: str, filename: str | None, fallback: str = ".audio") -> str:
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


def _escape_md(text: str) -> str:
    """Escape Telegram Markdown v1 special characters in plain text."""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, "\\" + ch)
    return text


async def _run_as_cancellable(user_id: int, coro) -> None:
    """Run coroutine as a cancellable task, registered in active_tasks."""
    task = asyncio.create_task(coro)
    active_tasks[user_id] = task
    try:
        await task
    except asyncio.CancelledError:
        pass
    finally:
        active_tasks.pop(user_id, None)


# ──────────────────────────────────────────────
# YouTube: inline keyboard
# ──────────────────────────────────────────────
_YT_LEVEL_MAP = {"b": "brief", "d": "detailed", "k": "keypoints"}
_YT_LEVEL_LABELS = {"brief": "Кратко", "detailed": "Подробно", "keypoints": "Тезисы"}


def _yt_summary_keyboard(cache_key: str) -> InlineKeyboardMarkup:
    """Build inline keyboard with summary detail level buttons."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Кратко", callback_data=f"yt:b:{cache_key}"),
        InlineKeyboardButton(text="Подробно", callback_data=f"yt:d:{cache_key}"),
        InlineKeyboardButton(text="Тезисы", callback_data=f"yt:k:{cache_key}"),
    ]])


# ──────────────────────────────────────────────
# Mode selection: inline keyboard
# ──────────────────────────────────────────────
_MODE_LABELS = {
    "chat": "💬 Чат",
    "transcribe": "🎙 Расшифровка",
    "note": "📓 Заметка",
}
_MODE_DESCRIPTIONS = {
    "chat": "💬 Режим: чат — расшифровка + ответ LLM.",
    "transcribe": "🎙 Режим: только расшифровка голоса (без LLM).",
    "note": "📓 Режим: Obsidian-заметка — голос → структурированная заметка в Markdown.",
}


def _mode_keyboard(current: str) -> InlineKeyboardMarkup:
    """Inline keyboard for mode selection. Current mode button is marked."""
    buttons = []
    for mode, label in _MODE_LABELS.items():
        text = f"✅ {label}" if mode == current else label
        buttons.append(InlineKeyboardButton(text=text, callback_data=f"mode:{mode}"))
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def _stop_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🛑 Стоп", callback_data="cancel"),
    ]])


def _get_audio_from_msg(msg: types.Message) -> tuple[str, str] | None:
    """Return (file_id, suffix) if msg contains audio/voice/video, else None."""
    if msg.voice:
        return msg.voice.file_id, ".ogg"
    if msg.audio:
        return msg.audio.file_id, _audio_suffix(msg.audio.mime_type, msg.audio.file_name)
    if msg.video_note:
        return msg.video_note.file_id, ".mp4"
    if msg.video:
        mime = msg.video.mime_type or ""
        suffix = ".webm" if "webm" in mime else ".mp4" if "mp4" in mime else (Path(msg.video.file_name or "video").suffix or ".mp4")
        return msg.video.file_id, suffix
    if msg.document:
        mime = msg.document.mime_type or ""
        if any(t in mime for t in ("audio", "video", "ogg", "webm", "mp4", "mp3", "m4a", "aac", "flac", "wav")):
            return msg.document.file_id, _audio_suffix(mime, msg.document.file_name)
    return None


# ──────────────────────────────────────────────
# YouTube: main processing pipeline
# ──────────────────────────────────────────────
async def _process_youtube(message: types.Message, url: str, diarize: bool):
    """Download YouTube audio, transcribe, send transcript file, summarize with inline buttons."""
    logger.info("YouTube: user_id=%d, url=%s, diarize=%s", message.from_user.id, url, diarize)
    processing_msg = await message.answer("📥 Загружаю аудио с YouTube...", reply_markup=_stop_keyboard())
    audio_path = None

    try:
        # 1. Download audio
        audio_path, title, duration = await download_yt_audio(url)
        duration_min = duration // 60
        await processing_msg.edit_text(
            f"🎙 Расшифровываю: {title} ({duration_min} мин)..."
        )

        # 2. Transcribe
        if diarize:
            if not HF_TOKEN:
                await processing_msg.edit_text(
                    "⚠️ Для распознавания спикеров нужен HF_TOKEN в .env. "
                    "Расшифровываю без спикеров..."
                )
                transcript_text = await transcribe(audio_path)
            else:
                await processing_msg.edit_text(
                    f"🎙 Расшифровываю со спикерами: {title} ({duration_min} мин)..."
                )
                transcript_text = await transcribe_diarized(audio_path)
        else:
            transcript_text = await transcribe(audio_path)

        if not transcript_text.strip():
            await processing_msg.edit_text("🤷 Не удалось распознать речь в видео.", reply_markup=None)
            return

        # 3. Send transcript as .txt file
        transcript_bytes = transcript_text.encode("utf-8")
        safe_title = re.sub(r'[^\w\s-]', '', title)[:50].strip() or "transcript"
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
                await message.answer(summary[i:i + 4000])
            await message.answer(
                "Выберите формат саммари:",
                reply_markup=_yt_summary_keyboard(cache_key),
            )
        else:
            await processing_msg.edit_text(
                full_msg,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=_yt_summary_keyboard(cache_key),
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
                    import shutil
                    shutil.rmtree(parent, ignore_errors=True)
            except OSError as e:
                logger.warning("Failed to clean up temp file %s: %s", audio_path, e)


# ──────────────────────────────────────────────
# Audio processing (shared by voice/audio/video handlers)
# ──────────────────────────────────────────────
async def _process_audio(message: types.Message, file_id: str, suffix: str):
    """Download audio file → transcribe → (LLM if chat mode) → reply."""
    logger.info("Audio: user_id=%d, type=%s, mode=%s, file_id=%s",
                message.from_user.id, suffix, get_mode(message.from_user.id), file_id[:20])
    processing_msg = await message.answer("🎙 Распознаю голос...", reply_markup=_stop_keyboard())

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

            note_md = (
                f"---\n"
                f"date: {date_str}\n"
                f"time: {time_str}\n"
                f"tags: {tags_yaml}\n"
                f"---\n\n"
                f"# {title}\n\n"
                f"{body}\n"
            )

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
        await processing_msg.edit_text(f"📝 _{_escape_md(user_text)}_\n\n⏳ Думаю...", parse_mode=ParseMode.MARKDOWN)

        response = await ask_ollama(message.from_user.id, user_text)

        full_text = f"📝 *Распознано:*\n_{_escape_md(user_text)}_\n\n🤖 *Ответ:*\n{response}"
        if len(full_text) > 4000:
            await processing_msg.edit_text(f"📝 _{_escape_md(user_text)}_", parse_mode=ParseMode.MARKDOWN, reply_markup=None)
            for i in range(0, len(response), 4000):
                await message.answer(response[i:i + 4000])
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
            await processing_msg.edit_text("❌ Файл слишком большой. Telegram Bot API ограничивает загрузку файлов до 20 МБ.", reply_markup=None)
        else:
            logger.exception("Audio processing error: user_id=%d", message.from_user.id)
            await processing_msg.edit_text(f"❌ Ошибка: {e}", reply_markup=None)


# ──────────────────────────────────────────────
# Commands
# ──────────────────────────────────────────────
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    logger.info("/start from user_id=%d (@%s)", message.from_user.id, message.from_user.username)
    if not is_allowed(message.from_user.id):
        return
    gdocs_line = "\n/savedoc — сохранять расшифровки в Google Docs" if gdocs_service else ""
    await message.answer(
        "👋 Привет! Я голосовой LLM-бот.\n\n"
        "🎤 Отправь голосовое сообщение — я распознаю и отвечу.\n"
        "⌨️ Или просто напиши текстом.\n"
        "🎬 Отправь ссылку на YouTube — получишь расшифровку и саммари.\n"
        "   Добавь слово «спикеры» для распознавания говорящих.\n\n"
        "Команды:\n"
        "/mode — выбрать режим (чат / расшифровка / Obsidian-заметка)\n"
        "/stop — остановить текущую обработку (или напиши «стоп»)\n"
        "/clear — очистить историю диалога\n"
        "/model — текущая модель\n"
        f"/ping — проверить Claude API\n"
        f"/limits — лимиты бесплатных API{gdocs_line}",
    )


@dp.message(Command("mode"))
async def cmd_mode(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    current = get_mode(message.from_user.id)
    logger.info("/mode user_id=%d, current=%s", message.from_user.id, current)
    await message.answer(
        f"Текущий режим: {_MODE_LABELS[current]}\nВыберите режим:",
        reply_markup=_mode_keyboard(current),
    )


@dp.callback_query(F.data.startswith("mode:"))
async def handle_mode_callback(callback: CallbackQuery):
    """Handle mode selection from inline keyboard."""
    new_mode = callback.data.split(":", 1)[1]
    if new_mode not in _MODE_LABELS:
        await callback.answer("Неизвестный режим.")
        return
    current = get_mode(callback.from_user.id)
    user_modes[callback.from_user.id] = new_mode
    logger.info("Mode change: user_id=%d: %s -> %s", callback.from_user.id, current, new_mode)
    await callback.answer(_MODE_LABELS[new_mode])
    await callback.message.edit_text(
        _MODE_DESCRIPTIONS[new_mode],
        reply_markup=_mode_keyboard(new_mode),
    )


@dp.callback_query(F.data == "cancel")
async def handle_cancel_callback(callback: CallbackQuery):
    """Handle 🛑 Стоп button press on a processing status message."""
    user_id = callback.from_user.id
    task = active_tasks.get(user_id)
    if task and not task.done():
        task.cancel()
        logger.info("Task cancelled via inline button: user_id=%d", user_id)
        await callback.answer("🛑 Остановлено")
    else:
        await callback.answer("Задача уже завершена")
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass


@dp.message(Command("clear"))
async def cmd_clear(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    logger.info("/clear from user_id=%d, history_size=%d", message.from_user.id, len(get_history(message.from_user.id)))
    clear_history(message.from_user.id)
    await message.answer("🗑 История диалога очищена.")


@dp.message(Command("model"))
async def cmd_model(message: types.Message):
    logger.info("/model from user_id=%d", message.from_user.id)
    if not is_allowed(message.from_user.id):
        return
    await message.answer(f"🤖 Модель: `{LLM_MODEL}`\n🎙 Whisper: `{WHISPER_MODEL}`", parse_mode=ParseMode.MARKDOWN)


@dp.message(Command("savedoc"))
async def cmd_savedoc(message: types.Message):
    logger.info("/savedoc from user_id=%d", message.from_user.id)
    if not is_allowed(message.from_user.id):
        return
    if gdocs_service is None:
        await message.answer(
            "❌ Google Docs не настроен.\n"
            "Добавь GDOCS_CREDENTIALS_FILE и GDOCS_DOCUMENT_ID в .env и перезапусти бота."
        )
        return
    enabled = not user_gdocs.get(message.from_user.id, False)
    user_gdocs[message.from_user.id] = enabled
    if enabled:
        await message.answer(
            f"📄 Сохранение в Google Docs включено.\n"
            f"Расшифровки будут добавляться в документ: https://docs.google.com/document/d/{GDOCS_DOCUMENT_ID}/edit"
        )
    else:
        await message.answer("🔇 Сохранение в Google Docs выключено.")


@dp.message(Command("stop"))
async def cmd_stop(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    user_id = message.from_user.id
    task = active_tasks.get(user_id)
    if task and not task.done():
        task.cancel()
        logger.info("Task cancelled via /stop: user_id=%d", user_id)
        await message.answer("🛑 Остановлено.")
    else:
        await message.answer("Нет активных задач.")


@dp.message(Command("ping"))
async def cmd_ping(message: types.Message):
    logger.info("/ping from user_id=%d", message.from_user.id)
    if not is_allowed(message.from_user.id):
        return
    try:
        model = await ping_llm()
        await message.answer(f"✅ LLM API доступна.\nМодель: {model}")
    except Exception as e:
        logger.error("Claude ping failed: %s", e)
        await message.answer(f"❌ Claude API недоступна: {e}")


@dp.message(Command("limits"))
async def cmd_limits(message: types.Message):
    logger.info("/limits from user_id=%d", message.from_user.id)
    if not is_allowed(message.from_user.id):
        return
    status_msg = await message.answer("🔍 Проверяю лимиты...")
    try:
        or_data, groq_data = None, None
        or_error, groq_error = None, None
        try:
            or_data = await check_openrouter()
        except Exception as e:
            logger.warning("OpenRouter limits check failed: %s", e)
            or_error = str(e)
        try:
            groq_data = await check_groq()
        except Exception as e:
            logger.warning("Groq limits check failed: %s", e)
            groq_error = str(e)

        text = format_limits_message(or_data, groq_data)
        errors = []
        if or_error:
            errors.append(f"OpenRouter: {or_error}")
        if groq_error:
            errors.append(f"Groq: {groq_error}")
        if errors:
            text += "\n\n⚠️ Ошибки:\n" + "\n".join(errors)

        await status_msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.exception("Limits command error")
        await status_msg.edit_text(f"❌ Ошибка: {e}")


# ──────────────────────────────────────────────
# Message handlers
# ──────────────────────────────────────────────
@dp.message(F.voice)
async def handle_voice(message: types.Message):
    """Process Telegram voice messages (.ogg)."""
    if not is_allowed(message.from_user.id):
        return
    await _run_as_cancellable(message.from_user.id, _process_audio(message, message.voice.file_id, ".ogg"))


@dp.message(F.audio)
async def handle_audio(message: types.Message):
    """Process audio file attachments (webm, mp3, m4a, etc.)."""
    if not is_allowed(message.from_user.id):
        return
    suffix = _audio_suffix(message.audio.mime_type, message.audio.file_name)
    await _run_as_cancellable(message.from_user.id, _process_audio(message, message.audio.file_id, suffix))


@dp.message(F.video_note)
async def handle_video_note(message: types.Message):
    """Process video notes (round video messages, typically .mp4)."""
    if not is_allowed(message.from_user.id):
        return
    await _run_as_cancellable(message.from_user.id, _process_audio(message, message.video_note.file_id, ".mp4"))


@dp.message(F.document)
async def handle_document(message: types.Message):
    """Process document attachments that are audio/video files (webm, mp3, etc.)."""
    if not is_allowed(message.from_user.id):
        return
    mime = message.document.mime_type or ""
    if not any(t in mime for t in ("audio", "video", "ogg", "webm", "mp4", "mp3", "m4a", "aac", "flac", "wav")):
        await message.answer("⚠️ Поддерживаются только аудио/видео файлы.")
        return
    suffix = _audio_suffix(mime, message.document.file_name)
    await _run_as_cancellable(message.from_user.id, _process_audio(message, message.document.file_id, suffix))


@dp.message(F.video)
async def handle_video(message: types.Message):
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
    await _run_as_cancellable(message.from_user.id, _process_audio(message, message.video.file_id, suffix))


async def _process_text(message: types.Message):
    """Send text message to LLM and reply."""
    processing_msg = await message.answer("⏳ Думаю...", reply_markup=_stop_keyboard())
    try:
        response = await ask_ollama(message.from_user.id, message.text)

        if len(response) > 4000:
            await processing_msg.delete()
            for i in range(0, len(response), 4000):
                await message.answer(response[i:i + 4000])
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


@dp.message(F.text)
async def handle_text(message: types.Message):
    """Process regular text messages through LLM."""
    logger.info("Text: user_id=%d, len=%d", message.from_user.id, len(message.text))
    if not is_allowed(message.from_user.id):
        return
    if message.text.startswith("/"):
        logger.debug("Ignoring unknown command from user_id=%d: %s", message.from_user.id, message.text.split()[0])
        return

    # Stop command as plain text
    if message.text.strip().lower() in ("стоп", "stop"):
        user_id = message.from_user.id
        task = active_tasks.get(user_id)
        if task and not task.done():
            task.cancel()
            logger.info("Task cancelled via text stop: user_id=%d", user_id)
        else:
            await message.answer("Нет активных задач.")
        return

    # If replying to a message with audio — process that audio
    if message.reply_to_message:
        audio = _get_audio_from_msg(message.reply_to_message)
        if audio:
            file_id, suffix = audio
            await _run_as_cancellable(message.from_user.id, _process_audio(message, file_id, suffix))
            return

    # Check for YouTube URL
    yt_match = YT_URL_RE.search(message.text)
    if yt_match:
        video_id = yt_match.group(1)
        url = f"https://www.youtube.com/watch?v={video_id}"
        diarize = wants_diarize(message.text)
        await _run_as_cancellable(message.from_user.id, _process_youtube(message, url, diarize))
        return

    await _run_as_cancellable(message.from_user.id, _process_text(message))


@dp.callback_query(F.data.startswith("yt:"))
async def handle_yt_summary_callback(callback: CallbackQuery):
    """Handle inline button presses for YouTube summary detail levels."""
    logger.info("YT callback: user_id=%d, data=%s", callback.from_user.id, callback.data)
    await callback.answer()

    parts = callback.data.split(":")
    if len(parts) != 3:
        return

    _, level_code, cache_key = parts
    detail_level = _YT_LEVEL_MAP.get(level_code)
    if not detail_level:
        return

    entry = yt_transcripts.get(cache_key)
    if not entry:
        await callback.message.edit_text("⏰ Расшифровка устарела. Отправьте ссылку заново.")
        return

    await callback.message.edit_text("🤖 Генерирую саммари...", reply_markup=None)

    try:
        summary = await summarize_ollama(
            entry["transcript"], detail_level, entry["title"]
        )

        label = _YT_LEVEL_LABELS.get(detail_level, "")
        header = f"📋 *Саммари ({label}):*\n\n"
        full_msg = header + summary

        if len(full_msg) > 4000:
            await callback.message.edit_text(header, parse_mode=ParseMode.MARKDOWN)
            for i in range(0, len(summary), 4000):
                await callback.message.answer(summary[i:i + 4000])
            await callback.message.answer(
                "Выберите формат саммари:",
                reply_markup=_yt_summary_keyboard(cache_key),
            )
        else:
            await callback.message.edit_text(
                full_msg,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=_yt_summary_keyboard(cache_key),
            )

        entry["ts"] = time.time()  # refresh TTL

    except Exception as e:
        logger.exception("YouTube summary callback error")
        await callback.message.edit_text(
            f"❌ Ошибка при генерации саммари: {e}",
            reply_markup=_yt_summary_keyboard(cache_key),
        )


@dp.message()
async def handle_unhandled(message: types.Message):
    """Catch-all: log unhandled content types for debugging."""
    logger.warning(
        "Unhandled message: content_type=%s, document mime=%s name=%s",
        message.content_type,
        message.document.mime_type if message.document else None,
        message.document.file_name if message.document else None,
    )


# ──────────────────────────────────────────────
# Entrypoint
# ──────────────────────────────────────────────
async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set! Add it to .env")
        return
    logger.info("Starting bot... Model: %s, Whisper: %s (%s), Allowed users: %s, GDocs: %s",
                LLM_MODEL, WHISPER_MODEL, WHISPER_DEVICE,
                ALLOWED_USER_IDS or "all", "enabled" if gdocs_service else "disabled")
    commands = [
        BotCommand(command="mode", description="Выбрать режим (чат / расшифровка / заметка)"),
        BotCommand(command="stop", description="Остановить текущую обработку"),
        BotCommand(command="clear", description="Очистить историю диалога"),
        BotCommand(command="model", description="Текущая модель"),
        BotCommand(command="ping", description="Проверить LLM API"),
        BotCommand(command="limits", description="Лимиты бесплатных API"),
        BotCommand(command="start", description="Помощь"),
    ]
    if gdocs_service:
        commands.append(BotCommand(command="savedoc", description="Сохранять расшифровки в Google Docs"))
    try:
        await bot.set_my_commands(commands)
    except Exception as e:
        logger.warning("Failed to set bot commands: %s", e)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
