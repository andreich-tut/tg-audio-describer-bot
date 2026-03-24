"""
Keyboard builders and UI label constants.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from shared.config import DEFAULT_LANGUAGE
from shared.i18n import t

# YouTube summary levels
YT_LEVEL_MAP = {"b": "brief", "d": "detailed", "k": "keypoints"}

# Language codes and labels
LANGUAGE_CODES = {"ru": "🇷🇺 Русский", "en": "🇬🇧 English"}


def get_yt_level_labels(locale: str = DEFAULT_LANGUAGE) -> dict[str, str]:
    """Get YouTube level labels for a locale."""
    return {
        "brief": t("keyboards.youtube.brief", locale),
        "detailed": t("keyboards.youtube.detailed", locale),
        "keypoints": t("keyboards.youtube.keypoints", locale),
    }


def get_mode_labels(locale: str = DEFAULT_LANGUAGE) -> dict[str, str]:
    """Get mode labels for a locale."""
    return {
        "chat": t("keyboards.mode.chat", locale),
        "transcribe": t("keyboards.mode.transcribe", locale),
        "note": t("keyboards.mode.note", locale),
    }


def _get_mode_descriptions(locale: str = DEFAULT_LANGUAGE) -> dict[str, str]:
    """Get mode descriptions for a locale."""
    return {
        "chat": t("keyboards.mode_descriptions.chat", locale),
        "transcribe": t("keyboards.mode_descriptions.transcribe", locale),
        "note": t("keyboards.mode_descriptions.note", locale),
    }



def yt_summary_keyboard(cache_key: str, locale: str = DEFAULT_LANGUAGE) -> InlineKeyboardMarkup:
    """Build inline keyboard with summary detail level buttons."""
    labels = get_yt_level_labels(locale)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=labels["brief"], callback_data=f"yt:b:{cache_key}"),
                InlineKeyboardButton(text=labels["detailed"], callback_data=f"yt:d:{cache_key}"),
                InlineKeyboardButton(text=labels["keypoints"], callback_data=f"yt:k:{cache_key}"),
            ]
        ]
    )


def mode_keyboard(current: str, locale: str = DEFAULT_LANGUAGE) -> InlineKeyboardMarkup:
    """Inline keyboard for mode selection. Current mode button is marked."""
    labels = get_mode_labels(locale)
    buttons = []
    for mode, label in labels.items():
        text = f"✅ {label}" if mode == current else label
        buttons.append(InlineKeyboardButton(text=text, callback_data=f"mode:{mode}"))
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def stop_keyboard(locale: str = DEFAULT_LANGUAGE) -> InlineKeyboardMarkup:
    """Inline keyboard with stop button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("keyboards.stop", locale), callback_data="cancel"),
            ]
        ]
    )


def language_keyboard(current_lang: str, locale: str = DEFAULT_LANGUAGE) -> InlineKeyboardMarkup:
    """Inline keyboard for language selection. Current language is marked."""
    buttons = []
    for code, label in LANGUAGE_CODES.items():
        text = f"✅ {label}" if code == current_lang else label
        buttons.append(InlineKeyboardButton(text=text, callback_data=f"lang:{code}"))
    return InlineKeyboardMarkup(inline_keyboard=[buttons])
