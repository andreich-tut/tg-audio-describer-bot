"""
REST API endpoints for browsing Yandex.Disk folder structure.

Provides endpoints for:
- Listing folders at a specified path (lazy-loading friendly)
- Getting nested folder tree structure (shallow depth recommended)
"""

import logging
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from infrastructure.database.database import Database
from infrastructure.external_api.yandex_client import refresh_access_token
from infrastructure.external_api.yandex_disk_client import (
    build_folder_tree,
    list_folder,
)
from interfaces.webapp.dependencies import get_current_user_id, get_database
from interfaces.webapp.schemas import YandexDiskFolder, YandexDiskTree

router = APIRouter(tags=["yandex-disk"])
logger = logging.getLogger(__name__)


async def _get_yandex_token(user_id: int, db: Database) -> str:
    """
    Get valid Yandex OAuth access token for user.
    Automatically refreshes the token if expired.

    Raises:
        HTTPException(401): If no OAuth token found
        HTTPException(403): If token is invalid/expired and refresh fails
    """
    token_data = await db.get_oauth_token(user_id, "yandex")
    if not token_data:
        raise HTTPException(
            status_code=401,
            detail="Yandex.Disk OAuth not connected. Please connect your account first.",
        )

    # Check if token is expired and refresh if needed
    expires_at = token_data.get("expires_at")
    refresh_token = token_data.get("refresh_token")

    # Determine if token is expired
    is_expired = False
    if expires_at:
        # Handle both datetime objects and ISO format strings
        if isinstance(expires_at, datetime):
            is_expired = expires_at <= datetime.now()
        elif isinstance(expires_at, str):
            try:
                is_expired = datetime.fromisoformat(expires_at) <= datetime.now()
            except (ValueError, TypeError):
                # If parsing fails, assume not expired to avoid unnecessary refresh
                is_expired = False

    if refresh_token and is_expired:
        # Token is expired, try to refresh
        new_token = await refresh_access_token(refresh_token)
        if new_token:
            # Save refreshed token back to database
            await db.set_oauth_token(
                user_id,
                "yandex",
                access_token=new_token.access_token,
                refresh_token=new_token.refresh_token or refresh_token,
                expires_at=new_token.expires_at,
            )
            logger.info("Yandex.Disk token refreshed for user_id=%d", user_id)
            return new_token.access_token
        else:
            # Refresh failed
            raise HTTPException(
                status_code=403,
                detail="Yandex.Disk OAuth token expired. Please reconnect your account.",
            )

    return token_data["access_token"]


@router.get("/yadisk/folders", response_model=list[YandexDiskFolder])
async def list_yadisk_folders(
    path: str = Query(default="/", description="Folder path to list"),
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum items to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    user_id: int = Depends(get_current_user_id),
    db: Database = Depends(get_database),
) -> list[YandexDiskFolder]:
    """
    List contents of a Yandex.Disk folder.

    This endpoint is designed for **lazy-loading** on the frontend.
    Call it with specific folder paths when user expands a folder in the tree view.

    **Rate Limit Warning:** Yandex.Disk API limits requests to ~1 request/second.
    Use this endpoint for on-demand loading instead of fetching deep trees.
    """
    # Validate path to prevent traversal attacks
    if not path.startswith("/") and not path.startswith("disk:/"):
        raise HTTPException(
            status_code=400,
            detail="Path must start with '/' or 'disk:/'",
        )

    # Block path traversal attempts
    if ".." in path:
        raise HTTPException(
            status_code=400,
            detail="Path traversal is not allowed",
        )

    try:
        access_token = await _get_yandex_token(user_id, db)
        items = await list_folder(path, access_token, limit, offset)
        return [YandexDiskFolder(**item) for item in items]

    except HTTPException:
        # Re-raise HTTPExceptions from _get_yandex_token (401/403)
        raise
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise HTTPException(
                status_code=403,
                detail="Invalid or expired Yandex OAuth token. Please reconnect your account.",
            ) from e
        if e.response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=f"Folder not found: {path}",
            ) from e
        if e.response.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please wait a moment and try again.",
            ) from e
        logger.error("Yandex.Disk API error: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Yandex.Disk API error: {e.response.status_code}",
        ) from e
    except httpx.HTTPError as e:
        logger.error("Yandex.Disk request failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to connect to Yandex.Disk API",
        ) from e


@router.get("/yadisk/folders/tree", response_model=YandexDiskTree)
async def get_yadisk_folder_tree(
    root_path: str = Query(default="/", description="Root folder to start from"),
    depth: int = Query(default=1, ge=1, le=3, description="Maximum nesting depth"),
    user_id: int = Depends(get_current_user_id),
    db: Database = Depends(get_database),
) -> YandexDiskTree:
    """
    Get nested folder tree structure.

    **Warning:** Keep depth shallow (1-2) to respect Yandex's ~1 req/sec rate limit.
    Deep recursive fetching may trigger 429 errors.

    For better performance, use GET /yadisk/folders for lazy-loading on the frontend.
    """
    # Validate path to prevent traversal attacks
    if not root_path.startswith("/") and not root_path.startswith("disk:/"):
        raise HTTPException(
            status_code=400,
            detail="Path must start with '/' or 'disk:/'",
        )

    # Block path traversal attempts
    if ".." in root_path:
        raise HTTPException(
            status_code=400,
            detail="Path traversal is not allowed",
        )

    try:
        access_token = await _get_yandex_token(user_id, db)
        tree = await build_folder_tree(root_path, access_token, max_depth=depth)
        return YandexDiskTree(**tree)

    except HTTPException:
        # Re-raise HTTPExceptions from _get_yandex_token (401/403)
        raise
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise HTTPException(
                status_code=403,
                detail="Invalid or expired Yandex OAuth token. Please reconnect your account.",
            ) from e
        if e.response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=f"Folder not found: {root_path}",
            ) from e
        if e.response.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please wait a moment and try again.",
            ) from e
        logger.error("Yandex.Disk API error: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Yandex.Disk API error: {e.response.status_code}",
        ) from e
    except httpx.HTTPError as e:
        logger.error("Yandex.Disk request failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to connect to Yandex.Disk API",
        ) from e
