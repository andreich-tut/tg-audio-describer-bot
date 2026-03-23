"""
Command handlers: /start, /mode, /clear, /model, /savedoc, /stop, /ping, /limits
Callback handlers: mode:*, cancel
"""

from aiogram import F, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery

from config import (
    GDOCS_DOCUMENT_ID,
    LLM_MODEL,
    WHISPER_MODEL,
    is_allowed,
    logger,
)
from core.keyboards import MODE_DESCRIPTIONS, MODE_LABELS, mode_keyboard
from services.gdocs import gdocs_service
from services.limits import check_groq, check_openrouter, format_limits_message
from services.llm import ping_llm
from state import (
    active_tasks,
    clear_history,
    get_history,
    get_mode,
    user_gdocs,
    user_modes,
)

router = Router(name="commands")


@router.message(CommandStart())
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


@router.message(Command("mode"))
async def cmd_mode(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    current = get_mode(message.from_user.id)
    logger.info("/mode user_id=%d, current=%s", message.from_user.id, current)
    await message.answer(
        f"Текущий режим: {MODE_LABELS[current]}\nВыберите режим:",
        reply_markup=mode_keyboard(current),
    )


@router.callback_query(F.data.startswith("mode:"))
async def handle_mode_callback(callback: CallbackQuery):
    """Handle mode selection from inline keyboard."""
    new_mode = callback.data.split(":", 1)[1]
    if new_mode not in MODE_LABELS:
        await callback.answer("Неизвестный режим.")
        return
    current = get_mode(callback.from_user.id)
    user_modes[callback.from_user.id] = new_mode
    logger.info("Mode change: user_id=%d: %s -> %s", callback.from_user.id, current, new_mode)
    await callback.answer(MODE_LABELS[new_mode])
    await callback.message.edit_text(
        MODE_DESCRIPTIONS[new_mode],
        reply_markup=mode_keyboard(new_mode),
    )


@router.callback_query(F.data == "cancel")
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


@router.message(Command("clear"))
async def cmd_clear(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    logger.info("/clear from user_id=%d, history_size=%d", message.from_user.id, len(get_history(message.from_user.id)))
    clear_history(message.from_user.id)
    await message.answer("🗑 История диалога очищена.")


@router.message(Command("model"))
async def cmd_model(message: types.Message):
    logger.info("/model from user_id=%d", message.from_user.id)
    if not is_allowed(message.from_user.id):
        return
    await message.answer(f"🤖 Модель: `{LLM_MODEL}`\n🎙 Whisper: `{WHISPER_MODEL}`", parse_mode=ParseMode.MARKDOWN)


@router.message(Command("savedoc"))
async def cmd_savedoc(message: types.Message):
    logger.info("/savedoc from user_id=%d", message.from_user.id)
    if not is_allowed(message.from_user.id):
        return
    if gdocs_service is None:
        await message.answer(
            "❌ Google Docs не настроен.\nДобавь GDOCS_CREDENTIALS_FILE и GDOCS_DOCUMENT_ID в .env и перезапусти бота."
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


@router.message(Command("stop"))
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


@router.message(Command("ping"))
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


@router.message(Command("limits"))
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
