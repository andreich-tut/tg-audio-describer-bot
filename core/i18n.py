"""
Internationalization (i18n) service for multi-language support.
"""

import json
from pathlib import Path
from typing import Any

from config import DEFAULT_LANGUAGE, logger

# Cache for loaded translations
_translations: dict[str, dict] = {}

# Supported languages
SUPPORTED_LANGUAGES = {"ru", "en"}


def _load_locale(locale: str) -> dict:
    """Load translations from a locale JSON file."""
    if locale in _translations:
        return _translations[locale]

    locale_file = Path(__file__).parent.parent / "locales" / f"{locale}.json"
    if not locale_file.exists():
        logger.warning("Locale file not found: %s, falling back to en", locale_file)
        locale_file = Path(__file__).parent.parent / "locales" / "en.json"

    try:
        with open(locale_file, "r", encoding="utf-8") as f:
            _translations[locale] = json.load(f)
        logger.info("Loaded locale: %s", locale)
        return _translations[locale]
    except json.JSONDecodeError as e:
        logger.error("Failed to parse locale file %s: %s", locale_file, e)
        # Fallback to empty dict
        _translations[locale] = {}
        return {}


def get_text(locale: str, key: str, **kwargs: Any) -> str:
    """
    Get translated text by key with optional format arguments.

    Args:
        locale: Language code (e.g., 'en', 'ru')
        key: Dot-separated key path (e.g., 'commands.start.greeting')
        **kwargs: Format arguments for string interpolation

    Returns:
        Translated text with placeholders replaced, or the key if not found
    """
    data = _load_locale(locale)

    # Navigate through nested dict
    parts = key.split(".")
    value: Any = data
    for part in parts:
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            logger.debug("Translation key not found: %s.%s", locale, key)
            return key

    if not isinstance(value, str):
        logger.warning("Translation value is not a string: %s.%s = %r", locale, key, value)
        return key

    # Format with kwargs if provided
    if kwargs:
        try:
            return value.format(**kwargs)
        except KeyError as e:
            logger.warning("Missing format arg for %s.%s: %s", locale, key, e)
            return value

    return value


def detect_language_from_telegram(language_code: str | None) -> str:
    """
    Detect user's preferred language from Telegram's language_code.

    Telegram language codes: https://core.telegram.org/bots/api#user
    Examples: 'en', 'ru', 'uk', 'be', 'kk', 'de', 'fr', 'es', 'it', 'pt'

    Returns the closest supported language or DEFAULT_LANGUAGE.
    """
    if not language_code:
        return DEFAULT_LANGUAGE

    # Direct match
    if language_code in SUPPORTED_LANGUAGES:
        return language_code

    # Handle variants like 'en_US', 'ru_UA', etc.
    base_lang = language_code.split("_")[0].lower()
    if base_lang in SUPPORTED_LANGUAGES:
        return base_lang

    # Cyrillic languages fallback to Russian
    cyrillic_langs = {"uk", "be", "kk", "ky", "tg", "uz"}
    if language_code in cyrillic_langs or base_lang in cyrillic_langs:
        return "ru"

    # Default fallback
    return DEFAULT_LANGUAGE


def get_user_locale(user_id: int, telegram_language_code: str | None = None) -> str:
    """
    Get locale for a specific user.

    Priority:
    1. User's saved preference
    2. Telegram's language setting (if provided)
    3. DEFAULT_LANGUAGE from config

    Args:
        user_id: Telegram user ID
        telegram_language_code: User's language code from Telegram (e.g., 'en', 'ru', 'uk')
    """
    from state import get_language

    # Check if user has a saved preference
    saved_lang = get_language(user_id)
    if saved_lang and saved_lang in SUPPORTED_LANGUAGES:
        return saved_lang

    # Detect from Telegram settings
    if telegram_language_code:
        detected = detect_language_from_telegram(telegram_language_code)
        if detected in SUPPORTED_LANGUAGES:
            return detected

    return DEFAULT_LANGUAGE


# Convenience functions for common translations
def t(key: str, locale: str = DEFAULT_LANGUAGE, **kwargs: Any) -> str:
    """Shorthand for get_text with default locale."""
    return get_text(locale, key, **kwargs)


def t_ru(key: str, **kwargs: Any) -> str:
    """Shorthand for Russian translation."""
    return get_text("ru", key, **kwargs)


def t_en(key: str, **kwargs: Any) -> str:
    """Shorthand for English translation."""
    return get_text("en", key, **kwargs)
