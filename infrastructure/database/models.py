"""
SQLAlchemy models for the bot database.

Tables:
- users: Core user profile and preferences
- user_settings: Key-value settings (flexible, extensible)
- oauth_tokens: OAuth tokens (encrypted)
- conversations: Message history (optional persistence)
- free_uses: Free-tier usage counters
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class User(Base):
    """User profile and core preferences."""

    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="ru")
    mode: Mapped[str] = mapped_column(String(50), default="chat")
    is_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    settings: Mapped[list["UserSetting"]] = relationship(
        "UserSetting", back_populates="user", cascade="all, delete-orphan"
    )
    oauth_tokens: Mapped[list["OAuthToken"]] = relationship(
        "OAuthToken", back_populates="user", cascade="all, delete-orphan"
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation", back_populates="user", cascade="all, delete-orphan"
    )
    free_use: Mapped[Optional["FreeUse"]] = relationship(
        "FreeUse", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    bot_messages: Mapped[list["BotMessage"]] = relationship(
        "BotMessage", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(user_id={self.user_id}, language={self.language}, mode={self.mode})>"


class UserSetting(Base):
    """Key-value settings for users.

    Stores both simple string values and encrypted sensitive data.
    Complex types (dicts, lists) are JSON-encoded.
    """

    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    is_encrypted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="settings")

    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_user_settings_user_id_key"),
        Index("idx_user_settings_user_id", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<UserSetting(user_id={self.user_id}, key={self.key})>"


class OAuthToken(Base):
    """OAuth tokens for external services (Yandex, Google, etc.).

    All token fields are encrypted at rest.
    """

    __tablename__ = "oauth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # 'yandex', 'google'
    access_token: Mapped[str] = mapped_column(Text, nullable=False)  # encrypted
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # encrypted
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    token_meta: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON: login, email
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="oauth_tokens")

    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_oauth_tokens_user_provider"),
        Index("idx_oauth_tokens_user_id", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<OAuthToken(user_id={self.user_id}, provider={self.provider})>"


class Conversation(Base):
    """Conversation history messages.

    Stores user messages and assistant responses for context.
    Automatically trimmed to MAX_HISTORY entries per user.
    """

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # 'user' or 'assistant'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="conversations")

    __table_args__ = (Index("idx_conversations_user_timestamp", "user_id", "timestamp"),)

    def __repr__(self) -> str:
        return f"<Conversation(user_id={self.user_id}, role={self.role})>"


class FreeUse(Base):
    """Free-tier usage counter.

    Tracks number of free API requests per user.
    """

    __tablename__ = "free_uses"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="free_use")

    def __repr__(self) -> str:
        return f"<FreeUse(user_id={self.user_id}, count={self.count})>"


class BotMessage(Base):
    """Tracks bot/user message IDs for 48h deletion window."""

    __tablename__ = "bot_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger)
    direction: Mapped[str] = mapped_column(String(4))  # "in" or "out"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="bot_messages")

    __table_args__ = (Index("idx_bot_messages_user_created", "user_id", "created_at"),)

    def __repr__(self) -> str:
        return f"<BotMessage(user_id={self.user_id}, message_id={self.message_id}, direction={self.direction})>"
