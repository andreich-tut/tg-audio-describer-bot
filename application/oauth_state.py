"""
OAuth token operations and user creation.
"""

from datetime import datetime
from typing import Optional

from infrastructure.database import get_db


def _get_db():
    return get_db()


async def get_or_create_user(user_id: int, username: Optional[str] = None):
    """Get or create a user in the database."""
    db = _get_db()
    return await db.get_or_create_user(user_id, username)


async def get_oauth_token_async(user_id: int, provider: str) -> Optional[dict]:
    """Get OAuth tokens for a user."""
    db = _get_db()
    return await db.get_oauth_token(user_id, provider)


async def set_oauth_token_async(
    user_id: int,
    provider: str,
    access_token: str,
    refresh_token: Optional[str] = None,
    expires_at: Optional[datetime] = None,
    meta: Optional[dict] = None,
) -> None:
    """Set OAuth tokens for a user."""
    db = _get_db()
    await db.set_oauth_token(user_id, provider, access_token, refresh_token, expires_at, meta)


async def delete_oauth_token_async(user_id: int, provider: str) -> bool:
    """Delete OAuth tokens for a user."""
    db = _get_db()
    return await db.delete_oauth_token(user_id, provider)
