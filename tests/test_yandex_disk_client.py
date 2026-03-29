"""
Tests for the Yandex.Disk REST API client.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from infrastructure.external_api.yandex_disk_client import (
    _normalize_path,
    build_folder_tree,
    get_resource_info,
    list_folder,
)


class TestNormalizePath:
    """Tests for path normalization utility."""

    def test_root_path(self):
        assert _normalize_path("/") == "disk:/"

    def test_empty_path(self):
        assert _normalize_path("") == "disk:/"

    def test_already_normalized(self):
        assert _normalize_path("disk:/Documents") == "disk:/Documents"
        assert _normalize_path("disk:/") == "disk:/"

    def test_unix_absolute_path(self):
        assert _normalize_path("/Documents") == "disk:/Documents"
        assert _normalize_path("/ObsidianVault/Inbox") == "disk:/ObsidianVault/Inbox"

    def test_relative_path(self):
        assert _normalize_path("Documents") == "disk:/Documents"
        assert _normalize_path("folder/subfolder") == "disk:/folder/subfolder"


class TestListFolder:
    """Tests for list_folder function."""

    @pytest.mark.asyncio
    async def test_list_root_folder(self, mock_yandex_folder_response):
        """Test listing root folder contents."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = mock_yandex_folder_response

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value = mock_client

            result = await list_folder("/", "test_token")

            assert len(result) == 3
            assert result[0]["name"] == "Documents"
            assert result[0]["type"] == "dir"
            assert result[0]["path"] == "disk:/Documents"
            assert result[2]["name"] == "photo.jpg"
            assert result[2]["type"] == "file"

    @pytest.mark.asyncio
    async def test_list_subfolder(self, mock_yandex_folder_response):
        """Test listing a specific subfolder."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = mock_yandex_folder_response

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value = mock_client

            result = await list_folder("/Documents", "test_token")

            assert len(result) == 3
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert call_args[1]["params"]["path"] == "disk:/Documents"

    @pytest.mark.asyncio
    async def test_list_folder_with_pagination(self, mock_yandex_folder_response):
        """Test listing with custom limit and offset."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = mock_yandex_folder_response

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value = mock_client

            await list_folder("/", "test_token", limit=10, offset=5)

            call_args = mock_client.get.call_args
            assert call_args[1]["params"]["limit"] == 10
            assert call_args[1]["params"]["offset"] == 5

    @pytest.mark.asyncio
    async def test_list_folder_empty_response(self):
        """Test handling empty folder response."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"_embedded": {"items": []}}

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value = mock_client

            result = await list_folder("/", "test_token")

            assert result == []

    @pytest.mark.asyncio
    async def test_list_folder_http_error(self):
        """Test handling HTTP errors."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError("Not Found", request=MagicMock(), response=MagicMock(status_code=404))
        )

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value = mock_client

            with pytest.raises(httpx.HTTPStatusError):
                await list_folder("/", "test_token")

    @pytest.mark.asyncio
    async def test_list_folder_429_rate_limit(self):
        """Test handling rate limit error."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Too Many Requests", request=MagicMock(), response=MagicMock(status_code=429)
            )
        )

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value = mock_client

            with pytest.raises(httpx.HTTPStatusError):
                await list_folder("/", "test_token")


class TestGetResourceInfo:
    """Tests for get_resource_info function."""

    @pytest.mark.asyncio
    async def test_get_folder_info(self, mock_yandex_resource_response):
        """Test getting folder metadata."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = mock_yandex_resource_response

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value = mock_client

            result = await get_resource_info("/ObsidianVault", "test_token")

            assert result["name"] == "ObsidianVault"
            assert result["path"] == "disk:/ObsidianVault"
            assert result["type"] == "dir"
            assert "created" in result
            assert "modified" in result

    @pytest.mark.asyncio
    async def test_get_file_info(self):
        """Test getting file metadata."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "name": "document.pdf",
            "path": "disk:/Documents/document.pdf",
            "type": "file",
        }

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value = mock_client

            result = await get_resource_info("/Documents/document.pdf", "test_token")

            assert result["name"] == "document.pdf"
            assert result["type"] == "file"

    @pytest.mark.asyncio
    async def test_get_resource_info_http_error(self):
        """Test handling HTTP errors."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError("Not Found", request=MagicMock(), response=MagicMock(status_code=404))
        )

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value = mock_client

            with pytest.raises(httpx.HTTPStatusError):
                await get_resource_info("/nonexistent", "test_token")


class TestBuildFolderTree:
    """Tests for build_folder_tree function."""

    @pytest.mark.asyncio
    async def test_build_tree_depth_0(self, mock_yandex_resource_response):
        """Test building tree with max_depth=0 (no children)."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = mock_yandex_resource_response

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value = mock_client

            result = await build_folder_tree("/ObsidianVault", "test_token", max_depth=0)

            assert result["name"] == "ObsidianVault"
            assert result["path"] == "disk:/ObsidianVault"
            assert result["type"] == "dir"
            assert result["children"] == []

    @pytest.mark.asyncio
    async def test_build_tree_depth_1(self, mock_yandex_resource_response, mock_yandex_folder_response):
        """Test building tree with max_depth=1."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        # First call: get_resource_info (root)
        # Second call: list_folder (root contents)
        # Third call: get_resource_info (Documents)
        # Fourth call: get_resource_info (ObsidianVault)
        mock_response.json.side_effect = [
            mock_yandex_resource_response,  # Root info
            mock_yandex_folder_response,  # Root contents
            {"name": "Documents", "path": "disk:/Documents", "type": "dir"},  # Documents info
            {"name": "ObsidianVault", "path": "disk:/ObsidianVault", "type": "dir"},  # ObsidianVault info
        ]

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value = mock_client

            result = await build_folder_tree("/", "test_token", max_depth=1)

            assert result["name"] == "ObsidianVault"
            # Documents and ObsidianVault (files are skipped)
            assert len(result["children"]) == 2

    @pytest.mark.asyncio
    async def test_build_tree_handles_list_folder_error(self, mock_yandex_resource_response):
        """Test that tree building continues even if list_folder fails."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        # First call succeeds (get_resource_info)
        # Second call fails (list_folder)
        mock_response.json.side_effect = [
            mock_yandex_resource_response,
            httpx.HTTPStatusError("Error", request=MagicMock(), response=MagicMock(status_code=500)),
        ]

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value = mock_client

            result = await build_folder_tree("/", "test_token", max_depth=1)

            assert result["name"] == "ObsidianVault"
            assert result["children"] == []  # Empty due to error

    @pytest.mark.asyncio
    async def test_build_tree_nested_structure(self):
        """Test building nested tree structure."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        # Simulate nested folder structure
        mock_response.json.side_effect = [
            # Root info
            {"name": "root", "path": "disk:/", "type": "dir"},
            # Root contents
            {"_embedded": {"items": [{"name": "Folder1", "path": "disk:/Folder1", "type": "dir"}]}},
            # Folder1 info
            {"name": "Folder1", "path": "disk:/Folder1", "type": "dir"},
            # Folder1 contents
            {"_embedded": {"items": [{"name": "SubFolder1", "path": "disk:/Folder1/SubFolder1", "type": "dir"}]}},
            # SubFolder1 info
            {"name": "SubFolder1", "path": "disk:/Folder1/SubFolder1", "type": "dir"},
            # SubFolder1 contents (empty)
            {"_embedded": {"items": []}},
        ]

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value = mock_client

            result = await build_folder_tree("/", "test_token", max_depth=2)

            assert result["name"] == "root"
            assert len(result["children"]) == 1
            assert result["children"][0]["name"] == "Folder1"
            assert len(result["children"][0]["children"]) == 1
            assert result["children"][0]["children"][0]["name"] == "SubFolder1"
