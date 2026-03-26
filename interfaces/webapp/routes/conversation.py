"""
Conversation history API endpoints.
"""

import logging

from fastapi import APIRouter, Depends

from infrastructure.database.database import Database
from interfaces.webapp.dependencies import get_current_user_id, get_database

router = APIRouter(tags=["conversation"])
logger = logging.getLogger(__name__)

MAX_HISTORY = 20


@router.get("/conversation")
async def get_conversation(
    user_id: int = Depends(get_current_user_id),
    db: Database = Depends(get_database),
) -> dict:
    messages = await db.get_conversation_history(user_id)
    serialized = [
        {
            "role": m["role"],
            "content": m["content"],
            "timestamp": m["timestamp"].isoformat() if m["timestamp"] else None,
        }
        for m in messages
    ]
    return {"messages": serialized, "max_history": MAX_HISTORY}


@router.delete("/conversation")
async def clear_conversation(
    user_id: int = Depends(get_current_user_id),
    db: Database = Depends(get_database),
) -> dict:
    deleted = await db.clear_conversation(user_id)
    logger.info("Conversation cleared: user_id=%d deleted=%d", user_id, deleted)
    return {"deleted": deleted}
