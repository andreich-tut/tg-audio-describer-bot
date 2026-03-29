"""
FastAPI dependency providers.
"""

import os

from fastapi import Header, HTTPException

from infrastructure.database.database import Database, get_db
from shared.config import ALLOWED_USER_IDS, BOT_TOKEN

from .auth import validate_init_data


async def get_database() -> Database:
    """Provide the database singleton."""
    return get_db()


async def get_current_user_id(
    x_telegram_init_data: str = Header(alias="X-Telegram-Init-Data"),
) -> int:
    """Validate Telegram initData and return the authenticated user_id."""
    dev_mode = os.getenv("WEBAPP_DEV_MODE", "").lower() == "true"

    user_data = validate_init_data(x_telegram_init_data, BOT_TOKEN)
    user_id = user_data.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="No user id in initData")
    user_id = int(user_id)

    # Skip allowed users check in dev mode
    if not dev_mode and ALLOWED_USER_IDS and user_id not in ALLOWED_USER_IDS:
        raise HTTPException(status_code=403, detail="Access denied")
    return user_id
