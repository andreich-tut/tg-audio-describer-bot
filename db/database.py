"""
Database service: SQLite + SQLAlchemy 2.0 async with connection pooling.

Provides:
- Database initialization and connection management
- CRUD operations for all models
- Migration from legacy JSON storage
- Backup/restore utilities
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.encryption import decrypt, encrypt
from db.models import Base, Conversation, FreeUse, OAuthToken, User, UserSetting

logger = logging.getLogger(__name__)

# Database path
DB_PATH = Path(__file__).parent.parent / "data" / "bot.db"

# Connection string for SQLite with aiosqlite
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"


class Database:
    """Async database service with CRUD operations."""

    def __init__(self, db_url: str = DATABASE_URL):
        self.db_url = db_url
        self.engine = create_async_engine(
            db_url,
            echo=False,
            future=True,
            pool_pre_ping=True,
        )
        self.async_session_maker = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    async def init_db(self) -> None:
        """Create all tables if they don't exist."""
        DB_PATH.parent.mkdir(exist_ok=True)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialized: %s", DB_PATH)

    async def close(self) -> None:
        """Close database connections."""
        await self.engine.dispose()
        logger.info("Database connections closed")

    # ── User operations ───────────────────────────────────────────────────────

    async def get_user(self, user_id: int) -> Optional[User]:
        """Get user by ID."""
        async with self.async_session_maker() as session:
            result = await session.execute(select(User).where(User.user_id == user_id))
            return result.scalar_one_or_none()

    async def get_or_create_user(self, user_id: int, username: Optional[str] = None) -> User:
        """Get existing user or create new one."""
        async with self.async_session_maker() as session:
            user = await self.get_user(user_id)
            if not user:
                user = User(user_id=user_id, username=username)
                session.add(user)
                await session.commit()
                await session.refresh(user)
                logger.info("Created new user: %d", user_id)
            elif username and user.username != username:
                user.username = username
                await session.commit()
            return user

    async def update_user(self, user_id: int, **kwargs) -> Optional[User]:
        """Update user fields."""
        async with self.async_session_maker() as session:
            await session.execute(update(User).where(User.user_id == user_id).values(**kwargs))
            await session.commit()
            return await self.get_user(user_id)

    async def delete_user(self, user_id: int) -> bool:
        """Delete user and all related data."""
        async with self.async_session_maker() as session:
            result = await session.execute(delete(User).where(User.user_id == user_id))
            await session.commit()
            deleted = result.rowcount > 0
            if deleted:
                logger.info("Deleted user: %d", user_id)
            return deleted

    # ── User settings operations ──────────────────────────────────────────────

    async def get_setting(self, user_id: int, key: str, default: Any = None) -> Any:
        """Get a user setting value."""
        async with self.async_session_maker() as session:
            result = await session.execute(
                select(UserSetting).where(
                    UserSetting.user_id == user_id,
                    UserSetting.key == key,
                )
            )
            setting = result.scalar_one_or_none()
            if not setting:
                return default

            if setting.is_encrypted:
                try:
                    return decrypt(setting.value)
                except Exception as e:
                    logger.error("Failed to decrypt setting %s: %s", key, e)
                    return default
            return setting.value

    async def get_setting_json(self, user_id: int, key: str, default: Any = None) -> Any:
        """Get a JSON-encoded user setting."""
        value = await self.get_setting(user_id, key)
        if value is None:
            return default
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default

    async def set_setting(self, user_id: int, key: str, value: Any, encrypt_value: bool = False) -> None:
        """Set a user setting value."""
        async with self.async_session_maker() as session:
            # Convert value to string
            if isinstance(value, (dict, list)):
                value_str = json.dumps(value, ensure_ascii=False, sort_keys=True)
            else:
                value_str = str(value)

            # Check if setting exists
            result = await session.execute(
                select(UserSetting).where(
                    UserSetting.user_id == user_id,
                    UserSetting.key == key,
                )
            )
            setting = result.scalar_one_or_none()

            if setting:
                setting.value = encrypt(value_str) if encrypt_value else value_str
                setting.is_encrypted = encrypt_value
                setting.updated_at = datetime.now(timezone.utc)
            else:
                setting = UserSetting(
                    user_id=user_id,
                    key=key,
                    value=encrypt(value_str) if encrypt_value else value_str,
                    is_encrypted=encrypt_value,
                )
                session.add(setting)

            await session.commit()

    async def set_setting_json(self, user_id: int, key: str, value: dict, encrypt_value: bool = False) -> None:
        """Set a JSON-encoded user setting."""
        value_str = json.dumps(value, ensure_ascii=False, sort_keys=True)
        await self.set_setting(user_id, key, value_str, encrypt_value=encrypt_value)

    async def delete_setting(self, user_id: int, key: str) -> bool:
        """Delete a user setting."""
        async with self.async_session_maker() as session:
            result = await session.execute(
                delete(UserSetting).where(
                    UserSetting.user_id == user_id,
                    UserSetting.key == key,
                )
            )
            await session.commit()
            return result.rowcount > 0

    async def delete_settings_section(self, user_id: int, keys: list[str]) -> int:
        """Delete multiple settings by keys."""
        async with self.async_session_maker() as session:
            result = await session.execute(
                delete(UserSetting).where(
                    UserSetting.user_id == user_id,
                    UserSetting.key.in_(keys),
                )
            )
            await session.commit()
            return result.rowcount

    async def get_all_settings(self, user_id: int) -> dict[str, Any]:
        """Get all settings for a user as a dict."""
        async with self.async_session_maker() as session:
            result = await session.execute(select(UserSetting).where(UserSetting.user_id == user_id))
            settings = result.scalars().all()
            data = {}
            for setting in settings:
                if setting.is_encrypted:
                    try:
                        data[setting.key] = decrypt(setting.value)
                    except Exception:
                        data[setting.key] = None
                else:
                    data[setting.key] = setting.value
            return data

    # ── OAuth token operations ────────────────────────────────────────────────

    async def get_oauth_token(self, user_id: int, provider: str) -> Optional[dict[str, Any]]:
        """Get OAuth tokens for a user."""
        async with self.async_session_maker() as session:
            result = await session.execute(
                select(OAuthToken).where(
                    OAuthToken.user_id == user_id,
                    OAuthToken.provider == provider,
                )
            )
            token = result.scalar_one_or_none()
            if not token:
                return None

            # Decrypt tokens
            try:
                access_token = decrypt(token.access_token)
                refresh_token = decrypt(token.refresh_token) if token.refresh_token else None
                meta = json.loads(token.token_meta) if token.token_meta else {}
            except Exception as e:
                logger.error("Failed to decrypt OAuth token: %s", e)
                return None

            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": token.expires_at,
                "token_meta": meta,
            }

    async def set_oauth_token(
        self,
        user_id: int,
        provider: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        meta: Optional[dict] = None,
    ) -> None:
        """Set OAuth tokens for a user."""
        async with self.async_session_maker() as session:
            # Check if token exists
            result = await session.execute(
                select(OAuthToken).where(
                    OAuthToken.user_id == user_id,
                    OAuthToken.provider == provider,
                )
            )
            token = result.scalar_one_or_none()

            # Encrypt tokens
            encrypted_access = encrypt(access_token)
            encrypted_refresh = encrypt(refresh_token) if refresh_token else None
            meta_json = json.dumps(meta, ensure_ascii=False, sort_keys=True) if meta else None

            if token:
                token.access_token = encrypted_access
                token.refresh_token = encrypted_refresh
                token.expires_at = expires_at
                token.token_meta = meta_json
                token.updated_at = datetime.now(timezone.utc)
            else:
                token = OAuthToken(
                    user_id=user_id,
                    provider=provider,
                    access_token=encrypted_access,
                    refresh_token=encrypted_refresh,
                    expires_at=expires_at,
                    token_meta=meta_json,
                )
                session.add(token)

            await session.commit()
            logger.info("Saved OAuth token: user_id=%d, provider=%s", user_id, provider)

    async def delete_oauth_token(self, user_id: int, provider: str) -> bool:
        """Delete OAuth tokens for a user."""
        async with self.async_session_maker() as session:
            result = await session.execute(
                delete(OAuthToken).where(
                    OAuthToken.user_id == user_id,
                    OAuthToken.provider == provider,
                )
            )
            await session.commit()
            deleted = result.rowcount > 0
            if deleted:
                logger.info("Deleted OAuth token: user_id=%d, provider=%s", user_id, provider)
            return deleted

    # ── Conversation operations ──────────────────────────────────────────────

    async def add_conversation_message(self, user_id: int, role: str, content: str) -> None:
        """Add a conversation message."""
        async with self.async_session_maker() as session:
            message = Conversation(user_id=user_id, role=role, content=content)
            session.add(message)
            await session.commit()

    async def get_conversation_history(self, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent conversation history."""
        async with self.async_session_maker() as session:
            result = await session.execute(
                select(Conversation)
                .where(Conversation.user_id == user_id)
                .order_by(Conversation.timestamp.desc())
                .limit(limit)
            )
            messages = result.scalars().all()
            # Return in chronological order (oldest first)
            return [{"role": m.role, "content": m.content, "timestamp": m.timestamp} for m in reversed(messages)]

    async def clear_conversation(self, user_id: int) -> int:
        """Clear conversation history for a user."""
        async with self.async_session_maker() as session:
            result = await session.execute(delete(Conversation).where(Conversation.user_id == user_id))
            await session.commit()
            deleted = result.rowcount
            logger.info("Cleared %d conversation messages for user %d", deleted, user_id)
            return deleted

    # ── Free uses operations ──────────────────────────────────────────────────

    async def get_free_uses(self, user_id: int) -> int:
        """Get free uses count for a user."""
        async with self.async_session_maker() as session:
            result = await session.execute(select(FreeUse).where(FreeUse.user_id == user_id))
            free_use = result.scalar_one_or_none()
            return free_use.count if free_use else 0

    async def set_free_uses(self, user_id: int, count: int) -> None:
        """Set free uses count for a user."""
        async with self.async_session_maker() as session:
            free_use = await session.get(FreeUse, user_id)
            if free_use:
                free_use.count = count
            else:
                free_use = FreeUse(user_id=user_id, count=count)
                session.add(free_use)
            await session.commit()

    async def increment_free_uses(self, user_id: int) -> int:
        """Increment free uses count and return new value."""
        async with self.async_session_maker() as session:
            free_use = await session.get(FreeUse, user_id)
            if free_use:
                free_use.count += 1
            else:
                free_use = FreeUse(user_id=user_id, count=1)
                session.add(free_use)
            await session.commit()
            return free_use.count

    # ── Migration from JSON ───────────────────────────────────────────────────

    async def migrate_from_json(self, json_data: dict) -> int:
        """Migrate data from legacy JSON format.

        Returns number of users migrated.
        """
        migrated_count = 0
        settings_data = json_data.get("settings", {})
        free_uses_data = json_data.get("free_uses", {})

        async with self.async_session_maker() as session:
            for user_id_str, user_settings in settings_data.items():
                user_id = int(user_id_str)
                migrated_count += 1

                # Create or get user
                user = await self.get_user(user_id)
                if not user:
                    user = User(user_id=user_id)
                    session.add(user)
                    await session.flush()

                # Migrate settings
                for key, value in user_settings.items():
                    # Determine if encryption is needed
                    encrypt_value = key == "llm_api_key"

                    # Special handling for OAuth token
                    if key == "yandex_oauth_token" and isinstance(value, dict):
                        # Extract and store as OAuthToken
                        meta = {
                            "login": value.get("login"),
                        }
                        oauth = OAuthToken(
                            user_id=user_id,
                            provider="yandex",
                            access_token=encrypt(value.get("access_token", "")),
                            refresh_token=encrypt(value.get("refresh_token")) if value.get("refresh_token") else None,
                            expires_at=value.get("expires_at"),
                            token_meta=json.dumps(meta, ensure_ascii=False),
                        )
                        session.add(oauth)
                        # Don't store as regular setting
                        continue

                    # Store as regular setting
                    if isinstance(value, (dict, list)):
                        value_str = json.dumps(value, ensure_ascii=False, sort_keys=True)
                    else:
                        value_str = str(value)

                    setting = UserSetting(
                        user_id=user_id,
                        key=key,
                        value=encrypt(value_str) if encrypt_value else value_str,
                        is_encrypted=encrypt_value,
                    )
                    session.add(setting)

            # Migrate free_uses
            for user_id_str, count in free_uses_data.items():
                user_id = int(user_id_str)
                free_use = FreeUse(user_id=user_id, count=count)
                session.add(free_use)

            await session.commit()

        logger.info("Migrated %d users from JSON to SQLite", migrated_count)
        return migrated_count


# Global database instance
_db: Optional[Database] = None


def get_db() -> Database:
    """Get or create global database instance."""
    global _db
    if _db is None:
        _db = Database()
    return _db
