"""
Conversation history CRUD operations.
"""

import logging
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from infrastructure.database.models import Conversation

logger = logging.getLogger(__name__)


class ConversationRepo:
    def __init__(self, session_maker: async_sessionmaker):
        self._session = session_maker

    async def add_conversation_message(self, user_id: int, role: str, content: str) -> None:
        async with self._session() as session:
            message = Conversation(user_id=user_id, role=role, content=content)
            session.add(message)
            await session.commit()

    async def get_conversation_history(self, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        async with self._session() as session:
            result = await session.execute(
                select(Conversation)
                .where(Conversation.user_id == user_id)
                .order_by(Conversation.timestamp.desc())
                .limit(limit)
            )
            messages = result.scalars().all()
            return [{"role": m.role, "content": m.content, "timestamp": m.timestamp} for m in reversed(messages)]

    async def clear_conversation(self, user_id: int) -> int:
        async with self._session() as session:
            result = await session.execute(delete(Conversation).where(Conversation.user_id == user_id))
            await session.commit()
            deleted = result.rowcount
            logger.info("Cleared %d conversation messages for user %d", deleted, user_id)
            return deleted
