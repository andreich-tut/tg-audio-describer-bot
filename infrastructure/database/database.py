"""
Database service: SQLite + SQLAlchemy 2.0 async with connection pooling.
"""

import logging
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from infrastructure.database.models import Base

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent.parent / "data" / "bot.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"


class Database:
    """Async database service. Delegates CRUD to repo objects."""

    def __init__(self, db_url: str = DATABASE_URL):
        self.db_url = db_url
        self.engine = create_async_engine(db_url, echo=False, future=True, pool_pre_ping=True)
        self.async_session_maker = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

        from infrastructure.database.bot_message_repo import BotMessageRepo
        from infrastructure.database.conversation_repo import ConversationRepo
        from infrastructure.database.oauth_repo import OAuthRepo
        from infrastructure.database.user_repo import UserRepo

        self._users = UserRepo(self.async_session_maker)
        self._conv = ConversationRepo(self.async_session_maker)
        self._oauth = OAuthRepo(self.async_session_maker)
        self._bot_messages = BotMessageRepo(self.async_session_maker)

    async def init_db(self) -> None:
        DB_PATH.parent.mkdir(exist_ok=True)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialized: %s", DB_PATH)

    async def close(self) -> None:
        await self.engine.dispose()
        logger.info("Database connections closed")

    # ── User / settings ───────────────────────────────────────────────────────
    get_user = property(lambda self: self._users.get_user)
    get_or_create_user = property(lambda self: self._users.get_or_create_user)
    update_user = property(lambda self: self._users.update_user)
    delete_user = property(lambda self: self._users.delete_user)
    get_setting = property(lambda self: self._users.get_setting)
    get_setting_json = property(lambda self: self._users.get_setting_json)
    set_setting = property(lambda self: self._users.set_setting)
    set_setting_json = property(lambda self: self._users.set_setting_json)
    delete_setting = property(lambda self: self._users.delete_setting)
    delete_settings_section = property(lambda self: self._users.delete_settings_section)
    get_all_settings = property(lambda self: self._users.get_all_settings)

    # ── Conversation ──────────────────────────────────────────────────────────
    add_conversation_message = property(lambda self: self._conv.add_conversation_message)
    get_conversation_history = property(lambda self: self._conv.get_conversation_history)
    clear_conversation = property(lambda self: self._conv.clear_conversation)

    # ── OAuth / free uses / migration ─────────────────────────────────────────
    get_oauth_token = property(lambda self: self._oauth.get_oauth_token)
    set_oauth_token = property(lambda self: self._oauth.set_oauth_token)
    delete_oauth_token = property(lambda self: self._oauth.delete_oauth_token)
    get_free_uses = property(lambda self: self._oauth.get_free_uses)
    set_free_uses = property(lambda self: self._oauth.set_free_uses)
    increment_free_uses = property(lambda self: self._oauth.increment_free_uses)
    migrate_from_json = property(lambda self: self._oauth.migrate_from_json)

    # ── Bot messages ──────────────────────────────────────────────────────────
    track_message = property(lambda self: self._bot_messages.track)
    get_deletable_messages = property(lambda self: self._bot_messages.get_deletable)
    purge_expired_messages = property(lambda self: self._bot_messages.purge_expired)


_db: Optional[Database] = None


def get_db() -> Database:
    """Get or create global database instance."""
    global _db
    if _db is None:
        _db = Database()
    return _db
