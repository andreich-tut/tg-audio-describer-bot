"""
Telegram Voice → LLM Bot
Stack: aiogram 3 + faster-whisper (local GPU) + Ollama

Send a voice message → bot transcribes via Whisper →
sends text to Ollama → returns the response.
Also works with regular text messages.
"""

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from application.state import initialize_state, shutdown_state
from infrastructure.storage.gdocs import gdocs_service
from interfaces.telegram.handlers.commands import router as commands_router
from interfaces.telegram.handlers.diagnostics import router as diagnostics_router
from interfaces.telegram.handlers.menu_button import router as menu_button_router
from interfaces.telegram.handlers.messages import router as messages_router
from interfaces.telegram.handlers.oauth_callback import router as oauth_callback_router
from interfaces.telegram.handlers.settings import router as settings_router
from interfaces.telegram.handlers.youtube_callbacks import router as youtube_callbacks_router
from interfaces.webapp.app import app as webapp
from shared.config import (
    ALLOWED_USER_IDS,
    BOT_TOKEN,
    DEFAULT_LANGUAGE,
    LLM_MODEL,
    WARP_PROXY,
    WEBAPP_PORT,
    WHISPER_DEVICE,
    WHISPER_MODEL,
    logger,
)
from shared.i18n import t

# Telegram Bot with WARP proxy
session = AiohttpSession(proxy=WARP_PROXY if WARP_PROXY else None) if WARP_PROXY else None
bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher(storage=MemoryStorage())

# Include routers: settings (FSM) first, oauth deep-link before plain /start,
# then commands, diagnostics, youtube callbacks, messages (catch-all last)
dp.include_routers(
    settings_router,
    oauth_callback_router,
    commands_router,
    diagnostics_router,
    menu_button_router,
    youtube_callbacks_router,
    messages_router,
)


async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set! Add it to .env")
        return

    # Initialize database and migrate legacy data
    await initialize_state()

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

    # Run uvicorn as a concurrent asyncio task with graceful shutdown
    import uvicorn

    config = uvicorn.Config(
        webapp,
        host="0.0.0.0",
        port=WEBAPP_PORT,
        log_config=None,  # Inherit bot's rotating file logging
    )
    server = uvicorn.Server(config)

    try:
        await asyncio.gather(
            dp.start_polling(bot),
            server.serve(),
        )
    except asyncio.CancelledError:
        pass  # Expected on shutdown
    finally:
        # 1. Signal uvicorn to stop accepting requests
        server.should_exit = True

        # 2. Allow in-flight requests to finish (prevents DB connection errors)
        await asyncio.sleep(0.5)

        # 3. Clean up bot and DB state last
        await shutdown_state()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
