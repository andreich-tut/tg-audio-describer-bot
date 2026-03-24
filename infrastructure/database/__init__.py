"""
Database package: SQLite + SQLAlchemy 2.0 with column-level encryption.

Provides persistent storage for:
- User settings and preferences
- OAuth tokens (encrypted)
- API keys (encrypted)
- Conversation history (optional persistence)
- Free-tier usage counters
"""

from infrastructure.database.database import DATABASE_URL, Database, get_db
from infrastructure.database.models import Base, Conversation, FreeUse, OAuthToken, User, UserSetting

__all__ = [
    "DATABASE_URL",
    "Base",
    "User",
    "UserSetting",
    "OAuthToken",
    "Conversation",
    "FreeUse",
    "Database",
    "get_db",
]
