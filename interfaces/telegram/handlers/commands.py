"""
Core command handlers: /start, /mode, /clear, /model, /savedoc, /stop
Callback handlers: mode:*, cancel
"""

from aiogram import F, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery

from application.state import (
    active_tasks,
    clear_history,
    get_history,
    get_mode,
    user_gdocs,
    user_modes,
)
from infrastructure.storage.gdocs import gdocs_service
from shared.config import (
    GDOCS_DOCUMENT_ID,
    LLM_MODEL,
    WHISPER_MODEL,
    is_allowed,
    logger,
)
from shared.i18n import t
from shared.keyboards import (
    _get_mode_descriptions,
    get_mode_labels,
    mode_keyboard,
)
from shared.utils import get_locale_from_callback, get_locale_from_message
from shared.version import __version__

router = Router(name="commands")


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    locale = await get_locale_from_message(message)
    from_user = message.from_user
    if not from_user:
        return
    logger.info("/start from user_id=%d (@%s)", from_user.id, from_user.username)
    if not is_allowed(from_user.id):
        return
    gdocs_line = "\n" + t("commands.start.savedoc", locale) if gdocs_service else ""
    await message.answer(
        t("commands.start.greeting", locale, version=__version__)
        + "\n\n"
        + t("commands.start.voice_instruction", locale)
        + "\n"
        + t("commands.start.text_instruction", locale)
        + "\n"
        + t("commands.start.youtube_instruction", locale)
        + "\n"
        + t("commands.start.youtube_speakers_note", locale)
        + "\n\n"
        + t("commands.start.commands_header", locale)
        + "\n"
        + t("commands.start.mode", locale)
        + "\n"
        + t("commands.start.stop", locale)
        + "\n"
        + t("commands.start.clear", locale)
        + "\n"
        + t("commands.start.model", locale)
        + "\n"
        + t("commands.start.ping", locale)
        + "\n"
        + t("commands.start.limits", locale)
        + "\n"
        + t("commands.start.lang", locale)
        + "\n"
        + t("commands.start.settings", locale)
        + gdocs_line,
    )


@router.message(Command("mode"))
async def cmd_mode(message: types.Message):
    locale = await get_locale_from_message(message)
    from_user = message.from_user
    if not from_user:
        return
    if not is_allowed(from_user.id):
        return
    current = await get_mode(from_user.id)
    logger.info("/mode user_id=%d, current=%s", from_user.id, current)
    await message.answer(
        t("commands.mode.current_mode", locale, mode=get_mode_labels(locale).get(current, current))
        + "\n"
        + t("commands.mode.select_mode", locale),
        reply_markup=mode_keyboard(current, locale),
    )


@router.callback_query(F.data.startswith("mode:"))
async def handle_mode_callback(callback: CallbackQuery):
    locale = await get_locale_from_callback(callback)
    from_user = callback.from_user
    if not from_user:
        await callback.answer()
        return
    if not callback.data:
        await callback.answer()
        return
    new_mode = callback.data.split(":", 1)[1]
    mode_labels = get_mode_labels(locale)
    if new_mode not in mode_labels:
        await callback.answer(t("commands.mode.unknown_mode", locale))
        return
    current = await get_mode(from_user.id)
    user_modes[from_user.id] = new_mode
    logger.info("Mode change: user_id=%d: %s -> %s", from_user.id, current, new_mode)
    await callback.answer(mode_labels[new_mode])
    await callback.message.edit_text(  # type: ignore[union-attr]
        _get_mode_descriptions(locale)[new_mode],
        reply_markup=mode_keyboard(new_mode, locale),
    )


@router.callback_query(F.data == "cancel")
async def handle_cancel_callback(callback: CallbackQuery):
    locale = await get_locale_from_callback(callback)
    from_user = callback.from_user
    if not from_user:
        await callback.answer()
        return
    user_id = from_user.id
    task = active_tasks.get(user_id)
    if task and not task.done():
        task.cancel()
        logger.info("Task cancelled via inline button: user_id=%d", user_id)
        await callback.answer(t("callbacks.cancel.stopped", locale))
    else:
        await callback.answer(t("callbacks.cancel.already_done", locale))
        try:
            if callback.message:
                await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
        except Exception:
            pass


@router.message(Command("clear"))
async def cmd_clear(message: types.Message):
    locale = await get_locale_from_message(message)
    from_user = message.from_user
    if not from_user:
        return
    if not is_allowed(from_user.id):
        return
    logger.info("/clear from user_id=%d, history_size=%d", from_user.id, len(get_history(from_user.id)))
    clear_history(from_user.id)
    await message.answer(t("commands.clear.history_cleared", locale))


@router.message(Command("model"))
async def cmd_model(message: types.Message):
    locale = await get_locale_from_message(message)
    from_user = message.from_user
    if not from_user:
        return
    logger.info("/model from user_id=%d", from_user.id)
    if not is_allowed(from_user.id):
        return
    await message.answer(
        t("commands.model.llm_model", locale, llm_model=LLM_MODEL)
        + "\n"
        + t("commands.model.whisper_model", locale, whisper_model=WHISPER_MODEL),
        parse_mode=ParseMode.MARKDOWN,
    )


@router.message(Command("savedoc"))
async def cmd_savedoc(message: types.Message):
    locale = await get_locale_from_message(message)
    from_user = message.from_user
    if not from_user:
        return
    logger.info("/savedoc from user_id=%d", from_user.id)
    if not is_allowed(from_user.id):
        return
    if gdocs_service is None:
        await message.answer(t("commands.savedoc.not_configured", locale))
        return
    enabled = not user_gdocs.get(from_user.id, False)
    user_gdocs[from_user.id] = enabled
    if enabled:
        document_url = f"https://docs.google.com/document/d/{GDOCS_DOCUMENT_ID}/edit"
        await message.answer(t("commands.savedoc.enabled", locale, document_url=document_url))
    else:
        await message.answer(t("commands.savedoc.disabled", locale))


@router.message(Command("stop"))
async def cmd_stop(message: types.Message):
    locale = await get_locale_from_message(message)
    from_user = message.from_user
    if not from_user:
        return
    if not is_allowed(from_user.id):
        return
    user_id = from_user.id
    task = active_tasks.get(user_id)
    if task and not task.done():
        task.cancel()
        logger.info("Task cancelled via /stop: user_id=%d", user_id)
        await message.answer(t("commands.stop.stopped", locale))
    else:
        await message.answer(t("commands.stop.no_active_tasks", locale))
