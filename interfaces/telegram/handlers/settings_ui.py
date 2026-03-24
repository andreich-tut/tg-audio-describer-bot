"""
Settings UI helpers: keyboard builders, text builders, metadata dicts.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from application.state import get_user_setting, get_user_setting_json
from shared.config import LLM_BASE_URL, LLM_MODEL, OBSIDIAN_INBOX_FOLDER, YANDEX_DISK_PATH
from shared.i18n import t

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

# Key → (label_i18n_key, submenu_name)
_KEY_META: dict[str, tuple[str, str]] = {
    "llm_api_key": ("settings.label_api_key", "llm"),
    "llm_base_url": ("settings.label_base_url", "llm"),
    "llm_model": ("settings.label_model", "llm"),
    "yadisk_path": ("settings.label_path", "yadisk"),
    "obsidian_vault_path": ("settings.label_vault_path", "obsidian"),
    "obsidian_inbox_folder": ("settings.label_inbox_folder", "obsidian"),
}


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "•••••••"
    return value[:4] + "..." + value[-4:]


def _val(user_id: int, key: str, fallback: str, locale: str, secret: bool = False) -> str:
    v = get_user_setting(user_id, key)
    if v:
        return _mask(v) if secret else v
    return f"{fallback} ({t('settings.global_default', locale)})"


# ── Keyboard builders ──────────────────────────────────────────────────────────


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
    oauth_token = get_user_setting_json(user_id, "yandex_oauth_token")
    is_connected = oauth_token and oauth_token.get("access_token")

    buttons = []
    if is_connected:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=t("settings.oauth_disconnect_btn", locale), callback_data="settings:oauth:disconnect"
                ),
            ]
        )
    else:
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
        inline_keyboard=[[InlineKeyboardButton(text=t("settings.cancel_btn", locale), callback_data="settings:cancel")]]
    )


# ── Text builders ──────────────────────────────────────────────────────────────


def _llm_text(user_id: int, locale: str) -> str:
    api_key = get_user_setting(user_id, "llm_api_key")
    api_key_display = _mask(api_key) if api_key else t("settings.not_set", locale)
    base_url = _val(user_id, "llm_base_url", LLM_BASE_URL, locale)
    model = _val(user_id, "llm_model", LLM_MODEL, locale)
    return f"{t('settings.llm_title', locale)}\n\nAPI Key: {api_key_display}\nBase URL: {base_url}\nModel: {model}"


def _yadisk_text(user_id: int, locale: str) -> str:
    oauth_token = get_user_setting_json(user_id, "yandex_oauth_token")
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


_SUBMENU_FNS = {
    "llm": (_llm_text, _llm_kb),
    "yadisk": (_yadisk_text, _yadisk_kb),
    "obsidian": (_obsidian_text, _obsidian_kb),
}
