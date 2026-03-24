"""
OAuth token and free-uses CRUD operations, plus JSON migration.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from infrastructure.database.encryption import decrypt, encrypt
from infrastructure.database.models import FreeUse, OAuthToken, User, UserSetting

logger = logging.getLogger(__name__)


class OAuthRepo:
    def __init__(self, session_maker: async_sessionmaker):
        self._session = session_maker

    async def get_oauth_token(self, user_id: int, provider: str) -> Optional[dict[str, Any]]:
        async with self._session() as session:
            result = await session.execute(
                select(OAuthToken).where(OAuthToken.user_id == user_id, OAuthToken.provider == provider)
            )
            token = result.scalar_one_or_none()
            if not token:
                return None
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
        async with self._session() as session:
            result = await session.execute(
                select(OAuthToken).where(OAuthToken.user_id == user_id, OAuthToken.provider == provider)
            )
            token = result.scalar_one_or_none()

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
        async with self._session() as session:
            result = await session.execute(
                delete(OAuthToken).where(OAuthToken.user_id == user_id, OAuthToken.provider == provider)
            )
            await session.commit()
            deleted = result.rowcount > 0
            if deleted:
                logger.info("Deleted OAuth token: user_id=%d, provider=%s", user_id, provider)
            return deleted

    async def get_free_uses(self, user_id: int) -> int:
        async with self._session() as session:
            result = await session.execute(select(FreeUse).where(FreeUse.user_id == user_id))
            free_use = result.scalar_one_or_none()
            return free_use.count if free_use else 0

    async def set_free_uses(self, user_id: int, count: int) -> None:
        async with self._session() as session:
            free_use = await session.get(FreeUse, user_id)
            if free_use:
                free_use.count = count
            else:
                free_use = FreeUse(user_id=user_id, count=count)
                session.add(free_use)
            await session.commit()

    async def increment_free_uses(self, user_id: int) -> int:
        async with self._session() as session:
            free_use = await session.get(FreeUse, user_id)
            if free_use:
                free_use.count += 1
            else:
                free_use = FreeUse(user_id=user_id, count=1)
                session.add(free_use)
            await session.commit()
            return free_use.count

    async def migrate_from_json(self, json_data: dict) -> int:
        """Migrate data from legacy JSON format. Returns number of users migrated."""
        migrated_count = 0
        settings_data = json_data.get("settings", {})
        free_uses_data = json_data.get("free_uses", {})

        async with self._session() as session:
            for user_id_str, user_settings in settings_data.items():
                user_id = int(user_id_str)
                migrated_count += 1

                result = await session.execute(select(User).where(User.user_id == user_id))
                user = result.scalar_one_or_none()
                if not user:
                    user = User(user_id=user_id)
                    session.add(user)
                    await session.flush()

                for key, value in user_settings.items():
                    encrypt_value = key == "llm_api_key"

                    if key == "yandex_oauth_token" and isinstance(value, dict):
                        meta = {"login": value.get("login")}
                        oauth = OAuthToken(
                            user_id=user_id,
                            provider="yandex",
                            access_token=encrypt(value.get("access_token", "")),
                            refresh_token=encrypt(value.get("refresh_token")) if value.get("refresh_token") else None,
                            expires_at=value.get("expires_at"),
                            token_meta=json.dumps(meta, ensure_ascii=False),
                        )
                        session.add(oauth)
                        continue

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

            for user_id_str, count in free_uses_data.items():
                user_id = int(user_id_str)
                free_use = FreeUse(user_id=user_id, count=count)
                session.add(free_use)

            await session.commit()

        logger.info("Migrated %d users from JSON to SQLite", migrated_count)
        return migrated_count
