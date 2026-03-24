"""
YouTube callback handlers: yt:* for summary detail level selection.
"""

import time

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery

from application.state import yt_transcripts
from infrastructure.external_api.llm_client import summarize_ollama
from shared.config import logger
from shared.i18n import t
from shared.keyboards import YT_LEVEL_MAP, get_yt_level_labels, yt_summary_keyboard
from shared.utils import get_locale_from_callback

router = Router(name="youtube_callbacks")


@router.callback_query(F.data.startswith("yt:"))
async def handle_yt_summary_callback(callback: CallbackQuery):
    """Handle inline button presses for YouTube summary detail levels."""
    locale = get_locale_from_callback(callback)
    logger.info("YT callback: user_id=%d, data=%s", callback.from_user.id, callback.data)
    await callback.answer()

    parts = callback.data.split(":")
    if len(parts) != 3:
        return

    _, level_code, cache_key = parts
    detail_level = YT_LEVEL_MAP.get(level_code)
    if not detail_level:
        return

    entry = yt_transcripts.get(cache_key)
    if not entry:
        await callback.message.edit_text(t("callbacks.youtube.expired", locale))
        return

    await callback.message.edit_text(t("callbacks.youtube.generate", locale), reply_markup=None)

    try:
        summary = await summarize_ollama(
            entry["transcript"], detail_level, entry["title"], locale, user_id=callback.from_user.id
        )

        label = get_yt_level_labels(locale).get(detail_level, "")
        header = t("pipelines.youtube.summary_format_header", locale, label=label)
        full_msg = header + summary

        if len(full_msg) > 4000:
            await callback.message.edit_text(header, parse_mode=ParseMode.MARKDOWN)
            for i in range(0, len(summary), 4000):
                await callback.message.answer(summary[i : i + 4000])
            await callback.message.answer(
                t("pipelines.youtube.select_format", locale),
                reply_markup=yt_summary_keyboard(cache_key, locale),
            )
        else:
            await callback.message.edit_text(
                full_msg,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=yt_summary_keyboard(cache_key, locale),
            )

        entry["ts"] = time.time()  # refresh TTL

    except Exception as e:
        logger.exception("YouTube summary callback error")
        await callback.message.edit_text(
            t("callbacks.youtube.error", locale, error=str(e)),
            reply_markup=yt_summary_keyboard(cache_key, locale),
        )
