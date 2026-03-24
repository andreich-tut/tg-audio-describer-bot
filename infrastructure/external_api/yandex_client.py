"""
Yandex OAuth authentication for Yandex.Disk WebDAV access.

Supports OAuth 2.0 flow with token refresh.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import httpx

from config import (
    YANDEX_OAUTH_CLIENT_ID,
    YANDEX_OAUTH_CLIENT_SECRET,
)

logger = logging.getLogger(__name__)

# Yandex OAuth endpoints
YANDEX_AUTH_URL = "https://oauth.yandex.ru/authorize"
YANDEX_TOKEN_URL = "https://oauth.yandex.ru/token"

# Required scopes for Yandex.Disk access
# login:info - Get user login information
# cloud_api:disk.app_folder - Access to app folder on Yandex.Disk
# Use space-separated format for multiple scopes
YANDEX_SCOPES = "login:info cloud_api:disk.app_folder"


@dataclass
class YandexToken:
    """Represents Yandex OAuth tokens."""

    access_token: str
    refresh_token: Optional[str] = None
    expires_at: Optional[datetime] = None
    token_type: str = "Bearer"

    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        # Consider token expired 1 minute before actual expiry
        return datetime.now() >= self.expires_at - timedelta(minutes=1)

    def to_dict(self) -> dict:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "token_type": self.token_type,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "YandexToken":
        expires_at = None
        if data.get("expires_at"):
            try:
                expires_at = datetime.fromisoformat(data["expires_at"])
            except (ValueError, TypeError):
                pass
        return cls(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_at=expires_at,
            token_type=data.get("token_type", "Bearer"),
        )


def get_oauth_url(state: str, bot_username: str) -> str:
    """Generate Yandex OAuth authorization URL with Telegram deep link redirect."""
    # Redirect to Telegram bot with start parameter containing code and state
    # Format: https://t.me/<bot>?start=oauth_<code>_<state>
    redirect_uri = f"https://t.me/{bot_username}"

    # URL encode the scope parameter (spaces become + or %20)
    from urllib.parse import urlencode

    params = {
        "response_type": "code",
        "client_id": YANDEX_OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": YANDEX_SCOPES,
        "state": state,
    }
    return f"{YANDEX_AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str, bot_username: str) -> Optional[YandexToken]:
    """Exchange authorization code for tokens."""
    if not YANDEX_OAUTH_CLIENT_ID or not YANDEX_OAUTH_CLIENT_SECRET:
        logger.error("Yandex OAuth credentials not configured")
        return None

    redirect_uri = f"https://t.me/{bot_username}"

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(
                YANDEX_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": YANDEX_OAUTH_CLIENT_ID,
                    "client_secret": YANDEX_OAUTH_CLIENT_SECRET,
                    "redirect_uri": redirect_uri,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            expires_in = data.get("expires_in", 86400)  # Default 24 hours

            token = YandexToken(
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token"),
                expires_at=datetime.now() + timedelta(seconds=expires_in),
                token_type=data.get("token_type", "Bearer"),
            )
            logger.info("Yandex OAuth token obtained successfully")
            return token

        except httpx.HTTPError as e:
            logger.error("Yandex OAuth token exchange failed: %s", e)
            return None
        except KeyError as e:
            logger.error("Invalid Yandex OAuth response: missing %s", e)
            return None


async def refresh_access_token(refresh_token: str) -> Optional[YandexToken]:
    """Refresh access token using refresh token."""
    if not YANDEX_OAUTH_CLIENT_ID or not YANDEX_OAUTH_CLIENT_SECRET:
        logger.error("Yandex OAuth credentials not configured")
        return None

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(
                YANDEX_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": YANDEX_OAUTH_CLIENT_ID,
                    "client_secret": YANDEX_OAUTH_CLIENT_SECRET,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            expires_in = data.get("expires_in", 86400)

            token = YandexToken(
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token", refresh_token),
                expires_at=datetime.now() + timedelta(seconds=expires_in),
                token_type=data.get("token_type", "Bearer"),
            )
            logger.info("Yandex OAuth token refreshed successfully")
            return token

        except httpx.HTTPError as e:
            logger.error("Yandex OAuth token refresh failed: %s", e)
            return None
        except KeyError as e:
            logger.error("Invalid Yandex OAuth refresh response: missing %s", e)
            return None


async def get_user_login(access_token: str) -> Optional[str]:
    """Get Yandex login (email) from OAuth token."""
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(
                "https://login.yandex.ru/info",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("login") or data.get("default_email")

        except httpx.HTTPError as e:
            logger.error("Failed to get Yandex user info: %s", e)
            return None
