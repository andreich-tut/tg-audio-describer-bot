"""
/settings command + FSM handlers for per-user API credentials and storage config.
"""

from urllib.parse import urlparse

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from application.state import clear_user_settings_section, set_user_setting
from interfaces.telegram.handlers.settings_oauth import router as _oauth_router
from interfaces.telegram.handlers.settings_ui import (
    _KEY_META,
    _PRIVILEGED_KEYS,
    _SECRET_KEYS,
    _SUBMENU_FNS,
    _SUBMENU_KEYS,
    _cancel_kb,
    _main_kb,
)
from shared.config import ALLOWED_USER_IDS, is_allowed, logger
from shared.i18n import t
from shared.utils import get_locale_from_callback, get_locale_from_message

router = Router(name="settings")
router.include_router(_oauth_router)


class SettingsStates(StatesGroup):
    waiting_for_value = State()

    @classmethod
    def all_states(cls) -> list[State]:
        return [cls.waiting_for_value]


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    locale = await get_locale_from_message(message)
    from_user = message.from_user
    if not from_user or not is_allowed(from_user.id):
        return
    logger.info("/settings from user_id=%d", from_user.id)
    await message.answer(t("settings.menu_title", locale), reply_markup=_main_kb(locale))


@router.callback_query(F.data == "settings:back")
async def cb_settings_back(callback: CallbackQuery, state: FSMContext):
    locale = await get_locale_from_callback(callback)
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(t("settings.menu_title", locale), reply_markup=_main_kb(locale))  # type: ignore[union-attr]


@router.callback_query(F.data.in_({"settings:llm", "settings:yadisk", "settings:obsidian"}))
async def cb_submenu(callback: CallbackQuery):
    locale = await get_locale_from_callback(callback)
    from_user = callback.from_user
    if not from_user or not callback.message or not callback.data:
        await callback.answer()
        return
    submenu = callback.data.split(":")[1]
    text_fn, kb_fn = _SUBMENU_FNS[submenu]
    await callback.answer()
    # _yadisk_kb is async, others are sync
    if submenu == "yadisk":
        keyboard = await kb_fn(locale, from_user.id)  # pyright: ignore[reportGeneralTypeIssues]
    else:
        keyboard = kb_fn(locale)  # pyright: ignore[reportGeneralTypeIssues]
    await callback.message.edit_text(await text_fn(from_user.id, locale), reply_markup=keyboard)  # type: ignore[union-attr]


@router.callback_query(F.data.startswith("settings:set:"))
async def cb_set_value(callback: CallbackQuery, state: FSMContext):
    locale = await get_locale_from_callback(callback)
    if not callback.data:
        await callback.answer()
        return
    key = callback.data.split(":", 2)[2]
    if key not in _KEY_META:
        await callback.answer()
        return

    if key in _PRIVILEGED_KEYS and ALLOWED_USER_IDS and callback.from_user.id not in ALLOWED_USER_IDS:
        await callback.answer(t("settings.access_denied", locale), show_alert=True)
        return

    label_key, submenu = _KEY_META[key]
    label = t(label_key, locale)
    await callback.answer()

    await state.set_state(SettingsStates.waiting_for_value)
    await state.update_data(key=key, submenu=submenu, msg_id=callback.message.message_id)  # type: ignore[arg-type]

    prompt = t("settings.send_value", locale, name=label)
    await callback.message.edit_text(prompt, reply_markup=_cancel_kb(locale))  # type: ignore[union-attr]


@router.callback_query(F.data == "settings:cancel", StateFilter(SettingsStates.waiting_for_value))
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    locale = await get_locale_from_callback(callback)
    from_user = callback.from_user
    if not from_user or not callback.message:
        await callback.answer()
        return
    data = await state.get_data()
    await state.clear()
    submenu = data.get("submenu", "llm")
    text_fn, kb_fn = _SUBMENU_FNS[submenu]
    await callback.answer()
    # _yadisk_kb is async, others are sync
    if submenu == "yadisk":
        keyboard = await kb_fn(locale, from_user.id)  # pyright: ignore[reportGeneralTypeIssues]
    else:
        keyboard = kb_fn(locale)  # pyright: ignore[reportGeneralTypeIssues]
    await callback.message.edit_text(await text_fn(from_user.id, locale), reply_markup=keyboard)  # type: ignore[union-attr]


@router.callback_query(F.data.startswith("settings:reset:"))
async def cb_reset_section(callback: CallbackQuery):
    locale = await get_locale_from_callback(callback)
    from_user = callback.from_user
    if not from_user or not callback.message or not callback.data:
        await callback.answer()
        return
    submenu = callback.data.split(":", 2)[2]
    if submenu not in _SUBMENU_KEYS:
        await callback.answer()
        return
    await clear_user_settings_section(from_user.id, _SUBMENU_KEYS[submenu])
    logger.info("Settings reset: user_id=%d, section=%s", from_user.id, submenu)
    await callback.answer(t("settings.settings_reset", locale, section=submenu))
    text_fn, kb_fn = _SUBMENU_FNS[submenu]
    # _yadisk_kb is async, others are sync
    if submenu == "yadisk":
        keyboard = await kb_fn(locale, from_user.id)  # pyright: ignore[reportGeneralTypeIssues]
    else:
        keyboard = kb_fn(locale)  # pyright: ignore[reportGeneralTypeIssues]
    text = await text_fn(from_user.id, locale)
    await callback.message.edit_text(text, reply_markup=keyboard)  # type: ignore[union-attr]


@router.message(StateFilter(SettingsStates.waiting_for_value))
async def handle_setting_value(message: Message, bot: Bot, state: FSMContext):
    locale = await get_locale_from_message(message)
    from_user = message.from_user
    if not from_user:
        return
    data = await state.get_data()
    key: str | None = data.get("key")
    submenu: str = data.get("submenu", "llm")
    msg_id: int | None = data.get("msg_id")
    await state.clear()

    if not key or not msg_id:
        return

    value = (message.text or "").strip()

    if key in _SECRET_KEYS:
        try:
            await message.delete()
        except Exception:
            pass

    if not value:
        error = t("settings.value_empty", locale)
        await message.answer(error)
        label_key, _ = _KEY_META.get(key, ("settings.label_api_key", submenu))
        label = t(label_key, locale)
        await state.set_state(SettingsStates.waiting_for_value)
        await state.update_data(key=key, submenu=submenu, msg_id=msg_id)
        try:
            await bot.edit_message_text(
                t("settings.send_value", locale, name=label),
                chat_id=message.chat.id,
                message_id=msg_id,
                reply_markup=_cancel_kb(locale),
            )
        except Exception:
            pass
        return

    if key == "llm_base_url":
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            await message.answer(t("settings.invalid_url", locale))
            label_key, _ = _KEY_META[key]
            label = t(label_key, locale)
            await state.set_state(SettingsStates.waiting_for_value)
            await state.update_data(key=key, submenu=submenu, msg_id=msg_id)
            try:
                await bot.edit_message_text(
                    t("settings.send_value", locale, name=label),
                    chat_id=message.chat.id,
                    message_id=msg_id,
                    reply_markup=_cancel_kb(locale),
                )
            except Exception:
                pass
            return

    if len(value) > 500:
        await message.answer(t("settings.value_too_long", locale, max=500))
        return

    await set_user_setting(from_user.id, key, value)
    label_key, _ = _KEY_META[key]
    label = t(label_key, locale)
    logger.info("Setting saved: user_id=%d, key=%s", from_user.id, key)

    text_fn, kb_fn = _SUBMENU_FNS[submenu]
    try:
        # _yadisk_kb is async, but this handler is only used for llm submenu
        if submenu == "yadisk":
            keyboard = await kb_fn(locale, from_user.id)  # pyright: ignore[reportGeneralTypeIssues]
        else:
            keyboard = kb_fn(locale)  # pyright: ignore[reportGeneralTypeIssues]
        text = await text_fn(from_user.id, locale)
        await bot.edit_message_text(
            text,
            chat_id=message.chat.id,
            message_id=msg_id,  # type: ignore[arg-type]
            reply_markup=keyboard,  # pyright: ignore[reportArgumentType]
        )
    except Exception:
        pass

    await message.answer(t("settings.value_saved", locale, name=label))
