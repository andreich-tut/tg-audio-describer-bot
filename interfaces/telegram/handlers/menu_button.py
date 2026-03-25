"""
Admin command to set the Mini App menu button.
Usage: /setmenu <url>
"""

from aiogram import Router, types
from aiogram.filters import Command

from shared.config import is_allowed, logger

router = Router(name="menu_button")


@router.message(Command("setmenu"))
async def cmd_set_menu(message: types.Message):
    """Set the Mini App menu button URL."""
    if not message.from_user or not is_allowed(message.from_user.id):
        return

    # Extract URL from command args
    url = message.text.split(maxsplit=1)[1] if message.text and " " in message.text else ""

    if not url:
        await message.answer(
            "Usage: /setmenu <url>\n"
            "Example: /setmenu https://your-domain.com/app/\n\n"
            "Or use /deletemenu to remove the button."
        )
        return

    try:
        from aiogram.types import MenuButtonWebApp, WebAppInfo

        if not message.bot:
            logger.error("Message bot is None")
            return

        await message.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Settings",
                web_app=WebAppInfo(url=url),
            )
        )
        logger.info("Mini App menu button set to: %s", url)
        await message.answer(f"✅ Mini App menu button set to:\n{url}")
    except Exception as e:
        logger.error("Failed to set menu button: %s", e)
        await message.answer(f"❌ Error: {e}")


@router.message(Command("deletemenu"))
async def cmd_delete_menu(message: types.Message):
    """Remove the Mini App menu button."""
    if not message.from_user or not is_allowed(message.from_user.id):
        return

    try:
        from aiogram.types import MenuButtonDefault

        if not message.bot:
            logger.error("Message bot is None")
            return

        await message.bot.set_chat_menu_button(menu_button=MenuButtonDefault())
        logger.info("Mini App menu button removed")
        await message.answer("✅ Mini App menu button removed")
    except Exception as e:
        logger.error("Failed to delete menu button: %s", e)
        await message.answer(f"❌ Error: {e}")


@router.message(Command("getmenu"))
async def cmd_get_menu(message: types.Message):
    """Get current menu button configuration."""
    if not message.from_user or not is_allowed(message.from_user.id):
        return

    try:
        if not message.bot:
            logger.error("Message bot is None")
            return

        menu = await message.bot.get_chat_menu_button()
        await message.answer(
            f"Current menu button:\nType: {menu.type}\nText: {getattr(menu, 'text', 'N/A')}\nURL: {getattr(menu, 'web_app', None)}"
        )
    except Exception as e:
        logger.error("Failed to get menu button: %s", e)
        await message.answer(f"❌ Error: {e}")
