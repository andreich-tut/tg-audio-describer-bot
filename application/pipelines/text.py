"""
Text message processing pipeline.
"""

import asyncio

from aiogram import types

from application.pipelines.audio import _check_free_tier
from infrastructure.external_api.llm_client import ask_ollama
from shared.config import logger
from shared.i18n import t
from shared.keyboards import stop_keyboard
from shared.utils import get_locale_from_message


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
