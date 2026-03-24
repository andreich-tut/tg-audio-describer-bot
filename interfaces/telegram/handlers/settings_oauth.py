"""
OAuth login/disconnect callbacks for Yandex.Disk settings.
"""

import uuid

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.methods import GetMe
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from application.state import delete_oauth_token_async
from infrastructure.external_api.yandex_client import get_oauth_url
from interfaces.telegram.handlers.settings_ui import _yadisk_kb, _yadisk_text
from shared.config import YANDEX_OAUTH_CLIENT_ID, logger
from shared.i18n import t
from shared.utils import get_locale_from_callback

router = Router(name="settings_oauth")


@router.callback_query(F.data == "settings:oauth:login")
async def cb_oauth_login(callback: CallbackQuery, state: FSMContext):
    locale = get_locale_from_callback(callback)

    if not YANDEX_OAUTH_CLIENT_ID:
        await callback.answer(t("settings.oauth.not_configured", locale), show_alert=True)
        return

    state_value = uuid.uuid4().hex[:16]
    await state.update_data(oauth_state=state_value)

    bot_info = await callback.bot(GetMe())
    bot_username = bot_info.username

    oauth_url = get_oauth_url(state_value, bot_username)

    await callback.answer()
    await callback.message.edit_text(
        t("settings.oauth.login_instruction_auto", locale),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t("settings.oauth.login_button", locale), url=oauth_url)],
                [InlineKeyboardButton(text=t("settings.back_btn", locale), callback_data="settings:back")],
            ]
        ),
    )


@router.callback_query(F.data == "settings:oauth:disconnect")
async def cb_oauth_disconnect(callback: CallbackQuery):
    locale = get_locale_from_callback(callback)
    user_id = callback.from_user.id

    await delete_oauth_token_async(user_id, "yandex")
    logger.info("OAuth disconnected: user_id=%d", user_id)

    await callback.answer(t("settings.oauth.disconnected", locale), show_alert=False)
    await callback.message.edit_text(
        _yadisk_text(user_id, locale),
        reply_markup=_yadisk_kb(locale, user_id),
    )
