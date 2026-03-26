"""
Message tracking middleware: logs all incoming/outgoing messages for 48h deletion window.
"""

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from infrastructure.database.database import get_db


class MessageTrackingMiddleware(BaseMiddleware):
    """Tracks all messages for potential deletion via /clear."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        db = get_db()

        # Track incoming user message
        if isinstance(event, Message) and event.from_user and event.chat:
            await db.track_message(
                user_id=event.from_user.id,
                chat_id=event.chat.id,
                message_id=event.message_id,
                direction="in",
            )

        result = await handler(event, data)

        # Track outgoing bot response
        if isinstance(result, Message) and result.chat:
            user_id = event.from_user.id if isinstance(event, Message) and event.from_user else 0
            await db.track_message(
                user_id=user_id,
                chat_id=result.chat.id,
                message_id=result.message_id,
                direction="out",
            )

        return result
