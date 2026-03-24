"""
/settings command + FSM handlers for per-user API credentials and storage config.
"""

from urllib.parse import urlparse

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from application.state import (
    clear_user_settings_section,
    get_user_setting,
    get_user_setting_json,
    set_user_setting,
)
from infrastructure.external_api.yandex_client import get_oauth_url
from shared.config import (
    ALLOWED_USER_IDS,
    LLM_BASE_URL,
    LLM_MODEL,
    OBSIDIAN_INBOX_FOLDER,
    YANDEX_DISK_PATH,
    YANDEX_OAUTH_CLIENT_ID,
    is_allowed,
    logger,
)
from shared.i18n import t
from shared.utils import get_locale_from_callback, get_locale_from_message

router = Router(name="settings")

# Keys that contain secrets — user's message will be deleted after reading
_SECRET_KEYS = {"llm_api_key"}

# Keys restricted to users in ALLOWED_USER_IDS (local path traversal risk)
_PRIVILEGED_KEYS = {"obsidian_vault_path"}

# Submenu membership
_SUBMENU_KEYS = {
    "llm": ["llm_api_key", "llm_base_url", "llm_model"],
    "yadisk": ["yadisk_path"],
    "obsidian": ["obsidian_vault_path", "obsidian_inbox_folder"],
}


class SettingsStates(StatesGroup):
    waiting_for_value = State()

    @classmethod
    def all_states(cls) -> list[State]:
        return [cls.waiting_for_value]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "•••••••"
    return value[:4] + "..." + value[-4:]


def _val(user_id: int, key: str, fallback: str, locale: str, secret: bool = False) -> str:
    v = get_user_setting(user_id, key)
    if v:
        return _mask(v) if secret else v
    return f"{fallback} ({t('settings.global_default', locale)})"


# ── Keyboard builders ─────────────────────────────────────────────────────────


def _main_kb(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("settings.llm_btn", locale), callback_data="settings:llm"),
                InlineKeyboardButton(text=t("settings.yadisk_btn", locale), callback_data="settings:yadisk"),
                InlineKeyboardButton(text=t("settings.obsidian_btn", locale), callback_data="settings:obsidian"),
            ]
        ]
    )


def _llm_kb(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("settings.set_api_key_btn", locale), callback_data="settings:set:llm_api_key"
                ),
                InlineKeyboardButton(
                    text=t("settings.set_base_url_btn", locale), callback_data="settings:set:llm_base_url"
                ),
            ],
            [
                InlineKeyboardButton(text=t("settings.set_model_btn", locale), callback_data="settings:set:llm_model"),
                InlineKeyboardButton(text=t("settings.reset_btn", locale), callback_data="settings:reset:llm"),
            ],
            [InlineKeyboardButton(text=t("settings.back_btn", locale), callback_data="settings:back")],
        ]
    )


def _yadisk_kb(locale: str, user_id: int) -> InlineKeyboardMarkup:
    """Yandex.Disk settings keyboard with OAuth login only (no direct credentials).

    Shows Connect button if not connected, Disconnect button if connected.
    """
    from application.state import get_user_setting_json

    oauth_token = get_user_setting_json(user_id, "yandex_oauth_token")
    is_connected = oauth_token and oauth_token.get("access_token")

    buttons = []

    if is_connected:
        # Show disconnect button only if connected
        buttons.append(
            [
                InlineKeyboardButton(
                    text=t("settings.oauth_disconnect_btn", locale), callback_data="settings:oauth:disconnect"
                ),
            ]
        )
    else:
        # Show login button only if not connected
        buttons.append(
            [
                InlineKeyboardButton(text=t("settings.oauth_login_btn", locale), callback_data="settings:oauth:login"),
            ]
        )

    buttons.append([InlineKeyboardButton(text=t("settings.back_btn", locale), callback_data="settings:back")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _obsidian_kb(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("settings.set_vault_path_btn", locale), callback_data="settings:set:obsidian_vault_path"
                ),
                InlineKeyboardButton(
                    text=t("settings.set_inbox_folder_btn", locale), callback_data="settings:set:obsidian_inbox_folder"
                ),
            ],
            [InlineKeyboardButton(text=t("settings.clear_btn", locale), callback_data="settings:reset:obsidian")],
            [InlineKeyboardButton(text=t("settings.back_btn", locale), callback_data="settings:back")],
        ]
    )


def _cancel_kb(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("settings.cancel_btn", locale), callback_data="settings:cancel"),
            ]
        ]
    )


# ── Submenu text builders ─────────────────────────────────────────────────────


def _llm_text(user_id: int, locale: str) -> str:
    api_key = get_user_setting(user_id, "llm_api_key")
    api_key_display = _mask(api_key) if api_key else t("settings.not_set", locale)
    base_url = _val(user_id, "llm_base_url", LLM_BASE_URL, locale)
    model = _val(user_id, "llm_model", LLM_MODEL, locale)
    return f"{t('settings.llm_title', locale)}\n\nAPI Key: {api_key_display}\nBase URL: {base_url}\nModel: {model}"


def _yadisk_text(user_id: int, locale: str) -> str:
    oauth_token = get_user_setting_json(user_id, "yandex_oauth_token")

    # Show OAuth login if available
    if oauth_token and oauth_token.get("access_token"):
        oauth_login = oauth_token.get("login", "Yandex User")
        login_display = f"{oauth_login} (OAuth)"
        status = (
            f"{t('settings.yadisk_connected', locale)}\n\n{t('settings.yadisk_login_label', locale)}: {login_display}"
        )
    else:
        status = t("settings.yadisk_not_connected", locale)

    path = _val(user_id, "yadisk_path", YANDEX_DISK_PATH, locale)

    return f"{t('settings.yadisk_title', locale)}\n\n{status}\n{t('settings.yadisk_path_label', locale)}: {path}"


def _obsidian_text(user_id: int, locale: str) -> str:
    vault = get_user_setting(user_id, "obsidian_vault_path") or t("settings.not_set", locale)
    inbox = _val(user_id, "obsidian_inbox_folder", OBSIDIAN_INBOX_FOLDER, locale)
    return f"{t('settings.obsidian_title', locale)}\n\nVault Path: {vault}\nInbox Folder: {inbox}"


# Key → (label_i18n_key, submenu_name, submenu_text_fn, submenu_kb_fn)
_KEY_META: dict[str, tuple[str, str]] = {
    "llm_api_key": ("settings.label_api_key", "llm"),
    "llm_base_url": ("settings.label_base_url", "llm"),
    "llm_model": ("settings.label_model", "llm"),
    "yadisk_path": ("settings.label_path", "yadisk"),
    "obsidian_vault_path": ("settings.label_vault_path", "obsidian"),
    "obsidian_inbox_folder": ("settings.label_inbox_folder", "obsidian"),
}

_SUBMENU_FNS = {
    "llm": (_llm_text, _llm_kb),
    "yadisk": (_yadisk_text, _yadisk_kb),
    "obsidian": (_obsidian_text, _obsidian_kb),
}


# ── Handlers ──────────────────────────────────────────────────────────────────


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    locale = get_locale_from_message(message)
    if not is_allowed(message.from_user.id):
        return
    logger.info("/settings from user_id=%d", message.from_user.id)
    await message.answer(t("settings.menu_title", locale), reply_markup=_main_kb(locale))


@router.callback_query(F.data == "settings:back")
async def cb_settings_back(callback: CallbackQuery, state: FSMContext):
    locale = get_locale_from_callback(callback)
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(t("settings.menu_title", locale), reply_markup=_main_kb(locale))


@router.callback_query(F.data.in_({"settings:llm", "settings:yadisk", "settings:obsidian"}))
async def cb_submenu(callback: CallbackQuery):
    locale = get_locale_from_callback(callback)
    submenu = callback.data.split(":")[1]
    text_fn, kb_fn = _SUBMENU_FNS[submenu]
    await callback.answer()

    # Pass user_id to keyboard builder for yadisk submenu
    if submenu == "yadisk":
        keyboard = kb_fn(locale, callback.from_user.id)
    else:
        keyboard = kb_fn(locale)

    await callback.message.edit_text(text_fn(callback.from_user.id, locale), reply_markup=keyboard)


@router.callback_query(F.data.startswith("settings:set:"))
async def cb_set_value(callback: CallbackQuery, state: FSMContext):
    locale = get_locale_from_callback(callback)
    key = callback.data.split(":", 2)[2]
    if key not in _KEY_META:
        await callback.answer()
        return

    # Access control for privileged keys (local paths)
    if key in _PRIVILEGED_KEYS and ALLOWED_USER_IDS and callback.from_user.id not in ALLOWED_USER_IDS:
        await callback.answer(t("settings.access_denied", locale), show_alert=True)
        return

    label_key, submenu = _KEY_META[key]
    label = t(label_key, locale)
    await callback.answer()

    await state.set_state(SettingsStates.waiting_for_value)
    await state.update_data(key=key, submenu=submenu, msg_id=callback.message.message_id)

    prompt = t("settings.send_value", locale, name=label)
    await callback.message.edit_text(prompt, reply_markup=_cancel_kb(locale))


@router.callback_query(F.data == "settings:cancel", StateFilter(SettingsStates.waiting_for_value))
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    locale = get_locale_from_callback(callback)
    data = await state.get_data()
    await state.clear()
    submenu = data.get("submenu", "llm")
    text_fn, kb_fn = _SUBMENU_FNS[submenu]
    await callback.answer()
    await callback.message.edit_text(text_fn(callback.from_user.id, locale), reply_markup=kb_fn(locale))


@router.callback_query(F.data.startswith("settings:reset:"))
async def cb_reset_section(callback: CallbackQuery):
    locale = get_locale_from_callback(callback)
    submenu = callback.data.split(":", 2)[2]
    if submenu not in _SUBMENU_KEYS:
        await callback.answer()
        return
    clear_user_settings_section(callback.from_user.id, _SUBMENU_KEYS[submenu])
    logger.info("Settings reset: user_id=%d, section=%s", callback.from_user.id, submenu)
    await callback.answer(t("settings.settings_reset", locale, section=submenu))
    text_fn, kb_fn = _SUBMENU_FNS[submenu]
    await callback.message.edit_text(text_fn(callback.from_user.id, locale), reply_markup=kb_fn(locale))


@router.callback_query(F.data == "settings:oauth:login")
async def cb_oauth_login(callback: CallbackQuery, state: FSMContext):
    """Initiate OAuth login flow."""
    locale = get_locale_from_callback(callback)

    if not YANDEX_OAUTH_CLIENT_ID:
        await callback.answer(t("settings.oauth.not_configured", locale), show_alert=True)
        return

    # Generate state parameter for security
    import uuid

    state_value = uuid.uuid4().hex[:16]

    # Store state in FSM to verify callback
    await state.update_data(oauth_state=state_value)

    # Get bot username for OAuth redirect
    from aiogram.methods import GetMe

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
    """Disconnect OAuth and remove stored token."""
    locale = get_locale_from_callback(callback)
    user_id = callback.from_user.id

    # Remove stored OAuth token using async database API
    from application.state import delete_oauth_token_async

    await delete_oauth_token_async(user_id, "yandex")
    logger.info("OAuth disconnected: user_id=%d", user_id)

    await callback.answer(t("settings.oauth.disconnected", locale), show_alert=False)

    # Update the settings message (show login button now)
    await callback.message.edit_text(
        _yadisk_text(user_id, locale),
        reply_markup=_yadisk_kb(locale, user_id),
    )


@router.message(StateFilter(SettingsStates.waiting_for_value))
async def handle_setting_value(message: Message, bot: Bot, state: FSMContext):
    locale = get_locale_from_message(message)
    data = await state.get_data()
    key = data.get("key")
    submenu = data.get("submenu", "llm")
    msg_id = data.get("msg_id")
    await state.clear()

    value = (message.text or "").strip()

    # Delete user message if it contains a secret
    if key in _SECRET_KEYS:
        try:
            await message.delete()
        except Exception:
            pass

    # Validate
    if not value:
        error = t("settings.value_empty", locale)
        await message.answer(error)
        # Re-enter waiting state
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

    # Save
    set_user_setting(message.from_user.id, key, value)
    label_key, _ = _KEY_META[key]
    label = t(label_key, locale)
    logger.info("Setting saved: user_id=%d, key=%s", message.from_user.id, key)

    # Edit the settings menu message back to the submenu
    text_fn, kb_fn = _SUBMENU_FNS[submenu]
    try:
        await bot.edit_message_text(
            text_fn(message.from_user.id, locale),
            chat_id=message.chat.id,
            message_id=msg_id,
            reply_markup=kb_fn(locale),
        )
    except Exception:
        pass

    await message.answer(t("settings.value_saved", locale, name=label))
