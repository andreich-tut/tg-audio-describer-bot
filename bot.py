"""
Telegram Voice → LLM Bot
Stack: aiogram 3 + faster-whisper (local GPU) + Ollama

Send a voice message → bot transcribes via Whisper →
sends text to Ollama → returns the response.
Also works with regular text messages.
"""

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

import state
from config import (
    ALLOWED_USER_IDS,
    BOT_TOKEN,
    DEFAULT_LANGUAGE,
    LLM_MODEL,
    WHISPER_DEVICE,
    WHISPER_MODEL,
    logger,
)
from core.i18n import t
from handlers.commands import router as commands_router
from handlers.messages import router as messages_router
from handlers.settings import router as settings_router
from handlers.youtube_callbacks import router as youtube_callbacks_router
from services.gdocs import gdocs_service

# Telegram Bot
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Include routers: settings (FSM) first, then commands, youtube callbacks, messages (catch-all last)
dp.include_routers(settings_router, commands_router, youtube_callbacks_router, messages_router)


async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set! Add it to .env")
        return
    state.load_user_settings()
    logger.info(
        "Starting bot... Model: %s, Whisper: %s (%s), Allowed users: %s, GDocs: %s",
        LLM_MODEL,
        WHISPER_MODEL,
        WHISPER_DEVICE,
        ALLOWED_USER_IDS or "all",
        "enabled" if gdocs_service else "disabled",
    )
    locale = DEFAULT_LANGUAGE
    commands = [
        BotCommand(
            command="mode",
            description=t("commands.start.mode", locale).split(" — ")[0].replace("/", ""),
        ),
        BotCommand(
            command="stop",
            description=t("commands.start.stop", locale).split(" — ")[0].replace("/", ""),
        ),
        BotCommand(
            command="clear",
            description=t("commands.start.clear", locale).split(" — ")[0].replace("/", ""),
        ),
        BotCommand(
            command="model",
            description=t("commands.start.model", locale).split(" — ")[0].replace("/", ""),
        ),
        BotCommand(
            command="ping",
            description=t("commands.start.ping", locale).split(" — ")[0].replace("/", ""),
        ),
        BotCommand(
            command="limits",
            description=t("commands.start.limits", locale).split(" — ")[0].replace("/", ""),
        ),
        BotCommand(
            command="lang",
            description=t("commands.start.lang", locale).split(" — ")[0].replace("/", ""),
        ),
        BotCommand(
            command="settings",
            description=t("commands.start.settings", locale),
        ),
        BotCommand(
            command="start",
            description=t("commands.start.greeting", locale).split("!")[0],
        ),
    ]
    if gdocs_service:
        commands.append(
            BotCommand(
                command="savedoc",
                description=t("commands.start.savedoc", locale).split(" — ")[0].replace("/", ""),
            )
        )
    try:
        await bot.set_my_commands(commands)
    except Exception as e:
        logger.warning("Failed to set bot commands: %s", e)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
