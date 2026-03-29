"""
Usage and rate-limit info API endpoints.
"""

import logging

from fastapi import APIRouter, Depends

from application.free_uses import FREE_USES_LIMIT
from application.services.rate_limiter import check_groq, check_openrouter
from infrastructure.database.database import Database
from interfaces.webapp.dependencies import get_current_user_id, get_database
from shared.config import LLM_BASE_URL, LLM_MODEL, WHISPER_BACKEND, WHISPER_MODEL

router = APIRouter(tags=["usage"])
logger = logging.getLogger(__name__)


@router.get("/usage", response_model=dict)
async def get_usage(
    user_id: int = Depends(get_current_user_id),
    db: Database = Depends(get_database),
) -> dict:
    openrouter_data, groq_data, free_uses_count, user = await _fetch_all(user_id, db)

    return {
        "openrouter": openrouter_data,
        "groq": groq_data,
        "free_uses": {
            "count": free_uses_count,
            "limit": FREE_USES_LIMIT,
        },
        "models": {
            "llm_model": LLM_MODEL,
            "llm_base_url": LLM_BASE_URL,
            "whisper_backend": WHISPER_BACKEND,
            "whisper_model": WHISPER_MODEL,
        },
        "user": {
            "mode": user.mode if user else None,
            "language": user.language if user else None,
        },
    }


async def _fetch_all(user_id: int, db: Database):
    import asyncio

    openrouter_data, groq_data, free_uses_count, user = await asyncio.gather(
        _safe(check_openrouter()),
        _safe(check_groq()),
        db.get_free_uses(user_id),
        db.get_user(user_id),
    )
    return openrouter_data, groq_data, free_uses_count, user


async def _safe(coro):
    """Run a coroutine, returning None on any exception."""
    try:
        return await coro
    except Exception:
        logger.exception("Error fetching usage data")
        return None
