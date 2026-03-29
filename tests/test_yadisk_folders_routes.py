"""
Tests for the Yandex.Disk folder browsing REST API endpoints.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from interfaces.webapp.app import app
from interfaces.webapp.dependencies import get_current_user_id, get_database


@pytest.fixture
def client():
    """Create test client for the FastAPI app with OAuth token."""
    mock_token = {
        "access_token": "test_access_token_12345",
        "refresh_token": "test_refresh_token_67890",
        "expires_at": None,
        "token_meta": {},
    }

    mock_db = AsyncMock()
    mock_db.get_oauth_token = AsyncMock(return_value=mock_token)

    with TestClient(app) as test_client:
        test_client.app.dependency_overrides[get_current_user_id] = lambda: 123456789  # type: ignore[attr-defined]
        test_client.app.dependency_overrides[get_database] = lambda: mock_db  # type: ignore[attr-defined]
        yield test_client
        test_client.app.dependency_overrides.clear()  # type: ignore[attr-defined]


@pytest.fixture
def client_no_oauth():
    """Create test client without OAuth token."""
    mock_db = AsyncMock()
    mock_db.get_oauth_token = AsyncMock(return_value=None)

    with TestClient(app) as test_client:
        test_client.app.dependency_overrides[get_current_user_id] = lambda: 123456789  # type: ignore[attr-defined]
        test_client.app.dependency_overrides[get_database] = lambda: mock_db  # type: ignore[attr-defined]
        yield test_client
        test_client.app.dependency_overrides.clear()  # type: ignore[attr-defined]


class TestListYandexFolders:
    """Tests for GET /api/v1/yadisk/folders endpoint."""

    def test_list_root_folder_success(self, client):
        """Test successful listing of root folder."""
        with patch("interfaces.webapp.routes.yadisk_folders.list_folder") as mock_list:
            mock_list.return_value = [
                {"name": "Documents", "path": "disk:/Documents", "type": "dir", "created": None, "modified": None},
                {"name": "photo.jpg", "path": "disk:/photo.jpg", "type": "file", "created": None, "modified": None},
            ]

            response = client.get("/api/v1/yadisk/folders")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["name"] == "Documents"
            assert data[0]["type"] == "dir"

    def test_list_folder_with_path(self, client):
        """Test listing a specific folder path."""
        with patch("interfaces.webapp.routes.yadisk_folders.list_folder") as mock_list:
            mock_list.return_value = [
                {"name": "file.pdf", "path": "disk:/Documents/file.pdf", "type": "file"},
            ]

            response = client.get("/api/v1/yadisk/folders?path=/Documents")

            assert response.status_code == 200
            mock_list.assert_called_once()

    def test_list_folder_with_pagination(self, client):
        """Test listing with pagination parameters."""
        with patch("interfaces.webapp.routes.yadisk_folders.list_folder") as mock_list:
            mock_list.return_value = []

            response = client.get("/api/v1/yadisk/folders?limit=10&offset=5")

            assert response.status_code == 200
            mock_list.assert_called_once_with("/", "test_access_token_12345", 10, 5)

    def test_list_folder_path_traversal_blocked(self, client):
        """Test that path traversal attempts are blocked."""
        response = client.get("/api/v1/yadisk/folders?path=../etc")

        assert response.status_code == 400
        assert "Path must start with" in response.json()["detail"]

    def test_list_folder_double_dot_blocked(self, client):
        """Test that paths with .. are blocked."""
        response = client.get("/api/v1/yadisk/folders?path=/Documents/../etc")

        assert response.status_code == 400
        assert "Path traversal is not allowed" in response.json()["detail"]

    def test_list_folder_no_oauth(self, client_no_oauth):
        """Test error when OAuth token is not connected."""
        response = client_no_oauth.get("/api/v1/yadisk/folders")

        assert response.status_code == 401
        assert "OAuth not connected" in response.json()["detail"]

    def test_list_folder_404(self, client):
        """Test handling folder not found error."""
        with patch("interfaces.webapp.routes.yadisk_folders.list_folder") as mock_list:
            mock_list.side_effect = httpx.HTTPStatusError(
                "Not Found",
                request=MagicMock(),
                response=MagicMock(status_code=404),
            )

            response = client.get("/api/v1/yadisk/folders?path=/nonexistent")

            assert response.status_code == 404
            assert "Folder not found" in response.json()["detail"]

    def test_list_folder_429_rate_limit(self, client):
        """Test handling rate limit error."""
        with patch("interfaces.webapp.routes.yadisk_folders.list_folder") as mock_list:
            mock_list.side_effect = httpx.HTTPStatusError(
                "Too Many Requests",
                request=MagicMock(),
                response=MagicMock(status_code=429),
            )

            response = client.get("/api/v1/yadisk/folders")

            assert response.status_code == 429
            assert "Rate limit exceeded" in response.json()["detail"]

    def test_list_folder_403_invalid_token(self, client):
        """Test handling invalid/expired token error."""
        with patch("interfaces.webapp.routes.yadisk_folders.list_folder") as mock_list:
            mock_list.side_effect = httpx.HTTPStatusError(
                "Unauthorized",
                request=MagicMock(),
                response=MagicMock(status_code=401),
            )

            response = client.get("/api/v1/yadisk/folders")

            assert response.status_code == 403
            assert "Invalid or expired" in response.json()["detail"]

    def test_list_folder_500_server_error(self, client):
        """Test handling generic server error."""
        with patch("interfaces.webapp.routes.yadisk_folders.list_folder") as mock_list:
            mock_list.side_effect = httpx.HTTPStatusError(
                "Internal Error",
                request=MagicMock(),
                response=MagicMock(status_code=500),
            )

            response = client.get("/api/v1/yadisk/folders")

            assert response.status_code == 500


class TestGetYandexFolderTree:
    """Tests for GET /api/v1/yadisk/folders/tree endpoint."""

    def test_get_tree_success(self, client):
        """Test successful folder tree retrieval."""
        with patch("interfaces.webapp.routes.yadisk_folders.build_folder_tree") as mock_tree:
            mock_tree.return_value = {
                "name": "root",
                "path": "disk:/",
                "type": "dir",
                "children": [
                    {
                        "name": "Documents",
                        "path": "disk:/Documents",
                        "type": "dir",
                        "children": [],
                    },
                ],
            }

            response = client.get("/api/v1/yadisk/folders/tree")

            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "root"
            assert len(data["children"]) == 1
            assert data["children"][0]["name"] == "Documents"

    def test_get_tree_with_custom_root(self, client):
        """Test tree with custom root path."""
        with patch("interfaces.webapp.routes.yadisk_folders.build_folder_tree") as mock_tree:
            mock_tree.return_value = {
                "name": "ObsidianVault",
                "path": "disk:/ObsidianVault",
                "type": "dir",
                "children": [],
            }

            response = client.get("/api/v1/yadisk/folders/tree?root_path=/ObsidianVault")

            assert response.status_code == 200
            mock_tree.assert_called_once()

    def test_get_tree_with_depth(self, client):
        """Test tree with custom depth."""
        with patch("interfaces.webapp.routes.yadisk_folders.build_folder_tree") as mock_tree:
            mock_tree.return_value = {"name": "root", "path": "disk:/", "type": "dir", "children": []}

            response = client.get("/api/v1/yadisk/folders/tree?depth=2")

            assert response.status_code == 200
            mock_tree.assert_called_once_with("/", "test_access_token_12345", max_depth=2)

    def test_get_tree_depth_validation(self, client):
        """Test that depth is validated (max 3)."""
        response = client.get("/api/v1/yadisk/folders/tree?depth=5")

        # FastAPI should reject depth > 3
        assert response.status_code == 422  # Validation error

    def test_get_tree_path_traversal_blocked(self, client):
        """Test that path traversal is blocked in tree endpoint."""
        response = client.get("/api/v1/yadisk/folders/tree?root_path=../etc")

        assert response.status_code == 400
        assert "Path must start with" in response.json()["detail"]

    def test_get_tree_no_oauth(self, client_no_oauth):
        """Test error when OAuth token is not connected."""
        response = client_no_oauth.get("/api/v1/yadisk/folders/tree")

        assert response.status_code == 401
        assert "OAuth not connected" in response.json()["detail"]

    def test_get_tree_404(self, client):
        """Test handling folder not found error."""
        with patch("interfaces.webapp.routes.yadisk_folders.build_folder_tree") as mock_tree:
            mock_tree.side_effect = httpx.HTTPStatusError(
                "Not Found",
                request=MagicMock(),
                response=MagicMock(status_code=404),
            )

            response = client.get("/api/v1/yadisk/folders/tree?root_path=/nonexistent")

            assert response.status_code == 404
            assert "Folder not found" in response.json()["detail"]

    def test_get_tree_429_rate_limit(self, client):
        """Test handling rate limit error."""
        with patch("interfaces.webapp.routes.yadisk_folders.build_folder_tree") as mock_tree:
            mock_tree.side_effect = httpx.HTTPStatusError(
                "Too Many Requests",
                request=MagicMock(),
                response=MagicMock(status_code=429),
            )

            response = client.get("/api/v1/yadisk/folders/tree")

            assert response.status_code == 429
            assert "Rate limit exceeded" in response.json()["detail"]


class TestEndpointAuthentication:
    """Tests for authentication requirements."""

    def test_list_folders_requires_auth(self):
        """Test that endpoint requires Telegram authentication."""
        with TestClient(app) as client:
            # Without proper X-Telegram-Init-Data header
            response = client.get("/api/v1/yadisk/folders")

            # Should fail with 401 (missing initData)
            assert response.status_code == 422  # Validation error for missing header

    def test_tree_endpoint_requires_auth(self):
        """Test that endpoint requires Telegram authentication."""
        with TestClient(app) as client:
            response = client.get("/api/v1/yadisk/folders/tree")

            # Should fail with 401 (missing initData)
            assert response.status_code == 422  # Validation error for missing header
