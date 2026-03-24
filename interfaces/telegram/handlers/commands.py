"""
Command handlers: /start, /mode, /clear, /model, /savedoc, /stop, /ping, /limits
Callback handlers: mode:*, cancel
"""

from aiogram import F, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery

from application.services.rate_limiter import check_groq, check_openrouter, format_limits_message
from application.state import (
    active_tasks,
    clear_history,
    get_history,
    get_language,
    get_mode,
    set_language,
    user_gdocs,
    user_modes,
)
from infrastructure.external_api.llm_client import ping_llm
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
    LANGUAGE_CODES,
    _get_mode_descriptions,
    get_mode_labels,
    language_keyboard,
    mode_keyboard,
)
from shared.utils import get_locale_from_callback, get_locale_from_message
from shared.version import __version__

router = Router(name="commands")


@router.message(CommandStart(deep_link="oauth_*"))
async def cmd_start_oauth(message: types.Message, state):
    """Handle OAuth callback from Yandex via Telegram deep link."""
    locale = get_locale_from_message(message)
    logger.info("OAuth callback from user_id=%d", message.from_user.id)

    # Parse deep link from CommandStart filter
    # The deep_link variable is extracted by the filter
    # Get the deep link parameter from the message
    deep_link = message.text.split()[-1] if " " in message.text else ""

    # Handle both "/start oauth_..." and just "oauth_..." formats
    if deep_link.startswith("/start"):
        deep_link = deep_link[6:].strip()
    if deep_link.startswith("oauth_"):
        deep_link = deep_link[6:]

    parts = deep_link.split("_")
    if len(parts) < 2:
        await message.answer(t("settings.oauth.no_code", locale))
        return

    # Reconstruct code (may contain underscores) and state
    state_param = parts[-1]
    code = "_".join(parts[:-1])

    if not code or not state_param:
        await message.answer(t("settings.oauth.no_code", locale))
        return

    # Verify OAuth state parameter (CSRF protection)
    fsm_state_data = await state.get_data()
    stored_state = fsm_state_data.get("oauth_state")

    if not stored_state or stored_state != state_param:
        logger.warning(
            "OAuth state mismatch: user_id=%d, received=%s, stored=%s", message.from_user.id, state_param, stored_state
        )
        await message.answer(t("settings.oauth.invalid_state", locale))
        await state.clear()
        return

    await message.answer(t("settings.oauth.exchanging", locale))

    # Exchange code for token
    from aiogram.methods import GetMe

    from infrastructure.external_api.yandex_client import exchange_code, get_user_login

    # Get bot username for redirect URI
    bot_info = await message.bot(GetMe())
    bot_username = bot_info.username

    token = await exchange_code(code, bot_username)

    if not token:
        await message.answer(t("settings.oauth.exchange_failed", locale))
        await state.clear()
        return

    # Get user login
    login = await get_user_login(token.access_token)

    if login:
        # Store OAuth token using async database API
        from application.state import set_oauth_token_async

        await set_oauth_token_async(
            message.from_user.id,
            "yandex",
            token.access_token,
            token.refresh_token,
            token.expires_at,
            {"login": login},
        )
        logger.info("OAuth login successful: user_id=%d, yandex_login=%s", message.from_user.id, login)

        # Clear FSM state and send success message with link to settings
        await state.clear()
        await message.answer(
            t("settings.oauth.success_auto", locale, login=login) + "\n\n" + t("settings.oauth.go_to_settings", locale),
        )
    else:
        await message.answer(t("settings.oauth.login_failed", locale))
        await state.clear()


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    locale = get_locale_from_message(message)
    logger.info("/start from user_id=%d (@%s)", message.from_user.id, message.from_user.username)
    if not is_allowed(message.from_user.id):
        return
    gdocs_line = "\n" + t("commands.start.savedoc", locale) if gdocs_service else ""
    await message.answer(
        t(
            "commands.start.greeting",
            locale,
            version=__version__,
        )
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
    locale = get_locale_from_message(message)
    if not is_allowed(message.from_user.id):
        return
    current = get_mode(message.from_user.id)
    logger.info("/mode user_id=%d, current=%s", message.from_user.id, current)
    await message.answer(
        t("commands.mode.current_mode", locale, mode=get_mode_labels(locale).get(current, current))
        + "\n"
        + t("commands.mode.select_mode", locale),
        reply_markup=mode_keyboard(current, locale),
    )


@router.callback_query(F.data.startswith("mode:"))
async def handle_mode_callback(callback: CallbackQuery):
    """Handle mode selection from inline keyboard."""
    locale = get_locale_from_callback(callback)
    new_mode = callback.data.split(":", 1)[1]
    mode_labels = get_mode_labels(locale)
    if new_mode not in mode_labels:
        await callback.answer(t("commands.mode.unknown_mode", locale))
        return
    current = get_mode(callback.from_user.id)
    user_modes[callback.from_user.id] = new_mode
    logger.info("Mode change: user_id=%d: %s -> %s", callback.from_user.id, current, new_mode)
    await callback.answer(mode_labels[new_mode])
    await callback.message.edit_text(
        _get_mode_descriptions(locale)[new_mode],
        reply_markup=mode_keyboard(new_mode, locale),
    )


@router.callback_query(F.data == "cancel")
async def handle_cancel_callback(callback: CallbackQuery):
    """Handle 🛑 Стоп button press on a processing status message."""
    locale = get_locale_from_callback(callback)
    user_id = callback.from_user.id
    task = active_tasks.get(user_id)
    if task and not task.done():
        task.cancel()
        logger.info("Task cancelled via inline button: user_id=%d", user_id)
        await callback.answer(t("callbacks.cancel.stopped", locale))
    else:
        await callback.answer(t("callbacks.cancel.already_done", locale))
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass


@router.message(Command("clear"))
async def cmd_clear(message: types.Message):
    locale = get_locale_from_message(message)
    if not is_allowed(message.from_user.id):
        return
    logger.info("/clear from user_id=%d, history_size=%d", message.from_user.id, len(get_history(message.from_user.id)))
    clear_history(message.from_user.id)
    await message.answer(t("commands.clear.history_cleared", locale))


@router.message(Command("model"))
async def cmd_model(message: types.Message):
    locale = get_locale_from_message(message)
    logger.info("/model from user_id=%d", message.from_user.id)
    if not is_allowed(message.from_user.id):
        return
    await message.answer(
        t("commands.model.llm_model", locale, llm_model=LLM_MODEL)
        + "\n"
        + t("commands.model.whisper_model", locale, whisper_model=WHISPER_MODEL),
        parse_mode=ParseMode.MARKDOWN,
    )


@router.message(Command("lang"))
async def cmd_lang(message: types.Message):
    locale = get_locale_from_message(message)
    logger.info("/lang from user_id=%d", message.from_user.id)
    if not is_allowed(message.from_user.id):
        return
    current_lang = get_language(message.from_user.id)
    current_label = LANGUAGE_CODES.get(current_lang, current_lang)
    await message.answer(
        t("commands.lang.current_language", locale, language=current_label)
        + "\n"
        + t("commands.lang.select_language", locale),
        reply_markup=language_keyboard(current_lang, locale),
    )


@router.callback_query(F.data.startswith("lang:"))
async def handle_lang_callback(callback: CallbackQuery):
    """Handle language selection from inline keyboard."""
    locale = get_locale_from_callback(callback)
    new_lang = callback.data.split(":", 1)[1]
    if new_lang not in LANGUAGE_CODES:
        await callback.answer(t("commands.lang.unknown_language", locale))
        return
    set_language(callback.from_user.id, new_lang)
    new_label = LANGUAGE_CODES[new_lang]
    logger.info("Language change: user_id=%d: -> %s", callback.from_user.id, new_lang)
    await callback.answer(t("commands.lang.language_changed", locale, language=new_label))
    await callback.message.edit_text(
        t("commands.lang.current_language", locale, language=new_label),
        reply_markup=language_keyboard(new_lang, locale),
    )


@router.message(Command("savedoc"))
async def cmd_savedoc(message: types.Message):
    locale = get_locale_from_message(message)
    logger.info("/savedoc from user_id=%d", message.from_user.id)
    if not is_allowed(message.from_user.id):
        return
    if gdocs_service is None:
        await message.answer(t("commands.savedoc.not_configured", locale))
        return
    enabled = not user_gdocs.get(message.from_user.id, False)
    user_gdocs[message.from_user.id] = enabled
    if enabled:
        document_url = f"https://docs.google.com/document/d/{GDOCS_DOCUMENT_ID}/edit"
        await message.answer(t("commands.savedoc.enabled", locale, document_url=document_url))
    else:
        await message.answer(t("commands.savedoc.disabled", locale))


@router.message(Command("stop"))
async def cmd_stop(message: types.Message):
    locale = get_locale_from_message(message)
    if not is_allowed(message.from_user.id):
        return
    user_id = message.from_user.id
    task = active_tasks.get(user_id)
    if task and not task.done():
        task.cancel()
        logger.info("Task cancelled via /stop: user_id=%d", user_id)
        await message.answer(t("commands.stop.stopped", locale))
    else:
        await message.answer(t("commands.stop.no_active_tasks", locale))


@router.message(Command("ping"))
async def cmd_ping(message: types.Message):
    locale = get_locale_from_message(message)
    logger.info("/ping from user_id=%d", message.from_user.id)
    if not is_allowed(message.from_user.id):
        return
    try:
        model = await ping_llm()
        await message.answer(t("commands.ping.success", locale, model=model))
    except Exception as e:
        logger.error("Claude ping failed: %s", e)
        await message.answer(t("commands.ping.error", locale, error=str(e)))


@router.message(Command("limits"))
async def cmd_limits(message: types.Message):
    locale = get_locale_from_message(message)
    logger.info("/limits from user_id=%d", message.from_user.id)
    if not is_allowed(message.from_user.id):
        return
    status_msg = await message.answer(t("commands.limits.checking", locale))
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

        text = format_limits_message(or_data, groq_data, locale)
        errors = []
        if or_error:
            errors.append(t("commands.limits.openrouter_error", locale, error=or_error))
        if groq_error:
            errors.append(t("commands.limits.groq_error", locale, error=groq_error))
        if errors:
            text += t("commands.limits.errors_header", locale) + "\n".join(errors)

        await status_msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.exception("Limits command error")
        await status_msg.edit_text(t("commands.limits.error", locale, error=str(e)))
