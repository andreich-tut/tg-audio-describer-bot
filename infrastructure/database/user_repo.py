"""
User and UserSettings CRUD operations.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from infrastructure.database.encryption import decrypt, encrypt
from infrastructure.database.models import User, UserSetting

logger = logging.getLogger(__name__)


class UserRepo:
    def __init__(self, session_maker: async_sessionmaker):
        self._session = session_maker

    async def get_user(self, user_id: int) -> Optional[User]:
        async with self._session() as session:
            result = await session.execute(select(User).where(User.user_id == user_id))
            return result.scalar_one_or_none()

    async def get_or_create_user(self, user_id: int, username: Optional[str] = None) -> User:
        async with self._session() as session:
            result = await session.execute(select(User).where(User.user_id == user_id))
            user = result.scalar_one_or_none()
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
        async with self._session() as session:
            await session.execute(update(User).where(User.user_id == user_id).values(**kwargs))
            await session.commit()
        return await self.get_user(user_id)

    async def delete_user(self, user_id: int) -> bool:
        async with self._session() as session:
            result = await session.execute(delete(User).where(User.user_id == user_id))
            await session.commit()
            deleted = result.rowcount > 0
            if deleted:
                logger.info("Deleted user: %d", user_id)
            return deleted

    async def get_setting(self, user_id: int, key: str, default: Any = None) -> Any:
        async with self._session() as session:
            result = await session.execute(
                select(UserSetting).where(UserSetting.user_id == user_id, UserSetting.key == key)
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
        value = await self.get_setting(user_id, key)
        if value is None:
            return default
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default

    async def set_setting(self, user_id: int, key: str, value: Any, encrypt_value: bool = False) -> None:
        async with self._session() as session:
            if isinstance(value, (dict, list)):
                value_str = json.dumps(value, ensure_ascii=False, sort_keys=True)
            else:
                value_str = str(value)

            result = await session.execute(
                select(UserSetting).where(UserSetting.user_id == user_id, UserSetting.key == key)
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
        value_str = json.dumps(value, ensure_ascii=False, sort_keys=True)
        await self.set_setting(user_id, key, value_str, encrypt_value=encrypt_value)

    async def delete_setting(self, user_id: int, key: str) -> bool:
        async with self._session() as session:
            result = await session.execute(
                delete(UserSetting).where(UserSetting.user_id == user_id, UserSetting.key == key)
            )
            await session.commit()
            return result.rowcount > 0

    async def delete_settings_section(self, user_id: int, keys: list[str]) -> int:
        async with self._session() as session:
            result = await session.execute(
                delete(UserSetting).where(UserSetting.user_id == user_id, UserSetting.key.in_(keys))
            )
            await session.commit()
            return result.rowcount

    async def get_all_settings(self, user_id: int) -> dict[str, Any]:
        async with self._session() as session:
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
