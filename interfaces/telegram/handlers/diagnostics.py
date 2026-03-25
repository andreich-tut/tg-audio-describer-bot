"""
Diagnostic commands: /ping, /limits, /lang and lang callback.
"""

from aiogram import F, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import CallbackQuery

from application.services.rate_limiter import check_groq, check_openrouter, format_limits_message
from application.state import set_language
from infrastructure.external_api.llm_client import ping_llm
from shared.config import is_allowed, logger
from shared.i18n import t
from shared.keyboards import LANGUAGE_CODES, language_keyboard
from shared.utils import get_locale_from_callback, get_locale_from_message

router = Router(name="diagnostics")


@router.message(Command("ping"))
async def cmd_ping(message: types.Message):
    locale = await get_locale_from_message(message)
    from_user = message.from_user
    if not from_user:
        return
    logger.info("/ping from user_id=%d", from_user.id)
    if not is_allowed(from_user.id):
        return
    try:
        model = await ping_llm()
        await message.answer(t("commands.ping.success", locale, model=model))
    except Exception as e:
        logger.error("Claude ping failed: %s", e)
        await message.answer(t("commands.ping.error", locale, error=str(e)))


@router.message(Command("limits"))
async def cmd_limits(message: types.Message):
    locale = await get_locale_from_message(message)
    from_user = message.from_user
    if not from_user:
        return
    logger.info("/limits from user_id=%d", from_user.id)
    if not is_allowed(from_user.id):
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

        if status_msg:
            await status_msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)  # type: ignore[union-attr]
    except Exception as e:
        logger.exception("Limits command error")
        if status_msg:
            await status_msg.edit_text(t("commands.limits.error", locale, error=str(e)))  # type: ignore[union-attr]


@router.message(Command("lang"))
async def cmd_lang(message: types.Message):
    locale = await get_locale_from_message(message)
    from_user = message.from_user
    if not from_user:
        return
    logger.info("/lang from user_id=%d", from_user.id)
    if not is_allowed(from_user.id):
        return
    from application.state import get_language

    current_lang = await get_language(from_user.id)
    current_label = LANGUAGE_CODES.get(current_lang, current_lang)
    await message.answer(
        t("commands.lang.current_language", locale, language=current_label)
        + "\n"
        + t("commands.lang.select_language", locale),
        reply_markup=language_keyboard(current_lang, locale),
    )


@router.callback_query(F.data.startswith("lang:"))
async def handle_lang_callback(callback: CallbackQuery):
    locale = await get_locale_from_callback(callback)
    from_user = callback.from_user
    if not from_user or not callback.message or not callback.data:
        await callback.answer()
        return
    new_lang = callback.data.split(":", 1)[1]
    if new_lang not in LANGUAGE_CODES:
        await callback.answer(t("commands.lang.unknown_language", locale))
        return

    await set_language(from_user.id, new_lang)
    new_label = LANGUAGE_CODES[new_lang]
    logger.info("Language change: user_id=%d: -> %s", from_user.id, new_lang)
    await callback.answer(t("commands.lang.language_changed", locale, language=new_label))
    await callback.message.edit_text(  # type: ignore[union-attr]
        t("commands.lang.current_language", locale, language=new_label),
        reply_markup=language_keyboard(new_lang, locale),
    )
