"""
Conversation history operations.
"""

import asyncio
import logging

from infrastructure.database import Database, get_db
from shared.config import MAX_HISTORY

logger = logging.getLogger(__name__)


def _get_db() -> Database:
    return get_db()


def add_to_history(user_id: int, role: str, content: str) -> None:
    """Add a message to conversation history (sync wrapper)."""
    db = _get_db()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        asyncio.run(_add_history_impl(db, user_id, role, content))
    else:
        if loop.is_running():
            asyncio.create_task(_add_history_impl(db, user_id, role, content))
        else:
            loop.run_until_complete(_add_history_impl(db, user_id, role, content))


async def _add_history_impl(db: Database, user_id: int, role: str, content: str) -> None:
    """Implementation of add_to_history."""
    await db.add_conversation_message(user_id, role, content)

    history = await db.get_conversation_history(user_id, limit=MAX_HISTORY + 5)
    if len(history) > MAX_HISTORY:
        to_delete = len(history) - MAX_HISTORY
        async with db.async_session_maker() as session:
            from sqlalchemy import delete, select

            from infrastructure.database.models import Conversation

            result = await session.execute(
                select(Conversation.id)
                .where(Conversation.user_id == user_id)
                .order_by(Conversation.timestamp.asc())
                .limit(to_delete)
            )
            ids_to_delete = result.scalars().all()
            if ids_to_delete:
                await session.execute(delete(Conversation).where(Conversation.id.in_(ids_to_delete)))
                await session.commit()


async def get_history_async(user_id: int) -> list[dict]:
    """Get conversation history for a user."""
    db = _get_db()
    return await db.get_conversation_history(user_id, limit=MAX_HISTORY)


def get_history(user_id: int) -> list[dict]:
    """Get conversation history for a user (sync wrapper)."""
    db = _get_db()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return asyncio.run(db.get_conversation_history(user_id, limit=MAX_HISTORY))
    else:
        if loop.is_running():
            return []
        return loop.run_until_complete(db.get_conversation_history(user_id, limit=MAX_HISTORY))


async def clear_history_async(user_id: int) -> int:
    """Clear conversation history for a user."""
    db = _get_db()
    return await db.clear_conversation(user_id)


def clear_history(user_id: int) -> int:
    """Clear conversation history for a user (sync wrapper)."""
    db = _get_db()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return asyncio.run(db.clear_conversation(user_id))
    else:
        if loop.is_running():
            return 0
        return loop.run_until_complete(db.clear_conversation(user_id))
