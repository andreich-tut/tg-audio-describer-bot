"""
Telegram Voice → LLM Bot
Stack: aiogram 3 + faster-whisper (local GPU) + Ollama

Send a voice message → bot transcribes via Whisper →
sends text to Ollama → returns the response.
Also works with regular text messages.
"""

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from config import (
    ALLOWED_USER_IDS,
    BOT_TOKEN,
    LLM_MODEL,
    WHISPER_DEVICE,
    WHISPER_MODEL,
    logger,
)
from handlers.commands import router as commands_router
from handlers.messages import router as messages_router
from handlers.youtube_callbacks import router as youtube_callbacks_router
from services.gdocs import gdocs_service

# Telegram Bot
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Include routers in order: commands -> youtube_callbacks -> messages (catch-all last)
dp.include_routers(commands_router, youtube_callbacks_router, messages_router)


async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set! Add it to .env")
        return
    logger.info(
        "Starting bot... Model: %s, Whisper: %s (%s), Allowed users: %s, GDocs: %s",
        LLM_MODEL,
        WHISPER_MODEL,
        WHISPER_DEVICE,
        ALLOWED_USER_IDS or "all",
        "enabled" if gdocs_service else "disabled",
    )
    commands = [
        BotCommand(command="mode", description="Выбрать режим (чат / расшифровка / заметка)"),
        BotCommand(command="stop", description="Остановить текущую обработку"),
        BotCommand(command="clear", description="Очистить историю диалога"),
        BotCommand(command="model", description="Текущая модель"),
        BotCommand(command="ping", description="Проверить LLM API"),
        BotCommand(command="limits", description="Лимиты бесплатных API"),
        BotCommand(command="start", description="Помощь"),
    ]
    if gdocs_service:
        commands.append(BotCommand(command="savedoc", description="Сохранять расшифровки в Google Docs"))
    try:
        await bot.set_my_commands(commands)
    except Exception as e:
        logger.warning("Failed to set bot commands: %s", e)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
