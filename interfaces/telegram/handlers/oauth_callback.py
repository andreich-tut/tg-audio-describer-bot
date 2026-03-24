"""
OAuth deep-link handler: /start oauth_<code>_<state>
"""

from aiogram import Router, types
from aiogram.filters import CommandStart

from application.state import set_oauth_token_async
from shared.config import logger
from shared.i18n import t
from shared.utils import get_locale_from_message

router = Router(name="oauth_callback")


@router.message(CommandStart(deep_link="oauth_*"))
async def cmd_start_oauth(message: types.Message, state):
    """Handle OAuth callback from Yandex via Telegram deep link."""
    locale = get_locale_from_message(message)
    logger.info("OAuth callback from user_id=%d", message.from_user.id)

    deep_link = message.text.split()[-1] if " " in message.text else ""
    if deep_link.startswith("/start"):
        deep_link = deep_link[6:].strip()
    if deep_link.startswith("oauth_"):
        deep_link = deep_link[6:]

    parts = deep_link.split("_")
    if len(parts) < 2:
        await message.answer(t("settings.oauth.no_code", locale))
        return

    state_param = parts[-1]
    code = "_".join(parts[:-1])

    if not code or not state_param:
        await message.answer(t("settings.oauth.no_code", locale))
        return

    fsm_state_data = await state.get_data()
    stored_state = fsm_state_data.get("oauth_state")

    if not stored_state or stored_state != state_param:
        logger.warning(
            "OAuth state mismatch: user_id=%d, received=%s, stored=%s",
            message.from_user.id,
            state_param,
            stored_state,
        )
        await message.answer(t("settings.oauth.invalid_state", locale))
        await state.clear()
        return

    await message.answer(t("settings.oauth.exchanging", locale))

    from aiogram.methods import GetMe

    from infrastructure.external_api.yandex_client import exchange_code, get_user_login

    bot_info = await message.bot(GetMe())
    bot_username = bot_info.username

    token = await exchange_code(code, bot_username)

    if not token:
        await message.answer(t("settings.oauth.exchange_failed", locale))
        await state.clear()
        return

    login = await get_user_login(token.access_token)

    if login:
        await set_oauth_token_async(
            message.from_user.id,
            "yandex",
            token.access_token,
            token.refresh_token,
            token.expires_at,
            {"login": login},
        )
        logger.info("OAuth login successful: user_id=%d, yandex_login=%s", message.from_user.id, login)
        await state.clear()
        await message.answer(
            t("settings.oauth.success_auto", locale, login=login) + "\n\n" + t("settings.oauth.go_to_settings", locale),
        )
    else:
        await message.answer(t("settings.oauth.login_failed", locale))
        await state.clear()
