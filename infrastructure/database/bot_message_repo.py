"""
BotMessage repository: tracks message IDs for 48h deletion window.
"""

from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from infrastructure.database.models import BotMessage


class BotMessageRepo:
    """Repository for bot message tracking."""

    def __init__(self, session_maker: async_sessionmaker):
        self._session_maker = session_maker

    async def track(self, user_id: int, chat_id: int, message_id: int, direction: str) -> None:
        """Track a message (in/out) for potential deletion."""
        async with self._session_maker() as session:
            session.add(
                BotMessage(
                    user_id=user_id,
                    chat_id=chat_id,
                    message_id=message_id,
                    direction=direction,
                )
            )
            await session.commit()

    async def get_deletable(self, user_id: int, chat_id: int) -> List[BotMessage]:
        """Get bot-sent messages within 48h window for deletion."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        async with self._session_maker() as session:
            result = await session.execute(
                select(BotMessage)
                .where(
                    BotMessage.user_id == user_id,
                    BotMessage.chat_id == chat_id,
                    BotMessage.direction == "out",
                    BotMessage.created_at >= cutoff,
                )
                .order_by(BotMessage.created_at.desc())
            )
            return list(result.scalars().all())

    async def purge_expired(self) -> None:
        """Delete records older than 48h — call from background task."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        async with self._session_maker() as session:
            await session.execute(delete(BotMessage).where(BotMessage.created_at < cutoff))
            await session.commit()
