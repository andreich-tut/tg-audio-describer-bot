"""
Pytest fixtures for the test suite.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from infrastructure.database.models import OAuthToken


@pytest.fixture
def mock_oauth_token():
    """Create a mock OAuth token for testing."""
    token = MagicMock(spec=OAuthToken)
    token.access_token = "test_access_token_12345"
    token.refresh_token = "test_refresh_token_67890"
    token.expires_at = datetime.now() + timedelta(hours=23)
    token.token_meta = '{"login": "test_user @yandex.ru"}'
    return token


@pytest.fixture
def mock_expired_oauth_token():
    """Create a mock expired OAuth token."""
    token = MagicMock(spec=OAuthToken)
    token.access_token = "expired_access_token"
    token.refresh_token = "test_refresh_token_67890"
    token.expires_at = datetime.now() - timedelta(hours=1)
    token.token_meta = '{"login": "test_user @yandex.ru"}'
    return token


@pytest.fixture
def mock_yandex_folder_response():
    """Mock response for Yandex.Disk folder listing."""
    return {
        "_embedded": {
            "items": [
                {
                    "name": "Documents",
                    "path": "disk:/Documents",
                    "type": "dir",
                    "created": "2024-01-15T10:30:00Z",
                    "modified": "2024-03-20T14:22:00Z",
                },
                {
                    "name": "ObsidianVault",
                    "path": "disk:/ObsidianVault",
                    "type": "dir",
                    "created": "2024-02-01T08:00:00Z",
                    "modified": "2024-03-28T16:45:00Z",
                },
                {
                    "name": "photo.jpg",
                    "path": "disk:/photo.jpg",
                    "type": "file",
                    "created": "2024-03-01T12:00:00Z",
                    "modified": "2024-03-01T12:00:00Z",
                },
            ]
        }
    }


@pytest.fixture
def mock_yandex_resource_response():
    """Mock response for Yandex.Disk resource info."""
    return {
        "name": "ObsidianVault",
        "path": "disk:/ObsidianVault",
        "type": "dir",
        "created": "2024-02-01T08:00:00Z",
        "modified": "2024-03-28T16:45:00Z",
    }


@pytest.fixture
def mock_httpx_get():
    """Mock httpx.AsyncClient.get for testing."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        yield mock_get


@pytest_asyncio.fixture
async def mock_db_with_oauth(mock_oauth_token):
    """Mock database with OAuth token."""
    mock_db = AsyncMock()
    mock_db.get_oauth_token = AsyncMock(return_value=mock_oauth_token)
    yield mock_db


@pytest_asyncio.fixture
async def mock_db_without_oauth():
    """Mock database without OAuth token."""
    mock_db = AsyncMock()
    mock_db.get_oauth_token = AsyncMock(return_value=None)
    yield mock_db


@pytest.fixture
def mock_user_data():
    """Mock Telegram user data."""
    return {"id": 123456789, "username": "test_user", "first_name": "Test User"}
