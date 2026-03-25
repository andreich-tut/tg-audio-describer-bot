"""
Yandex OAuth endpoints for the Mini App.

Flow:
  1. Frontend calls GET /api/v1/oauth/yandex/url → receives OAuth URL
  2. Frontend opens URL via Telegram.WebApp.openLink() (external browser)
  3. User authorises on Yandex
  4. Yandex redirects to GET /api/v1/oauth/yandex/callback?code=...&state=...
  5. Backend exchanges code, stores token, returns HTML that closes the tab
  6. Frontend detects visibility change → re-fetches /settings → shows connected
"""

import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from infrastructure.database.database import Database
from infrastructure.external_api.yandex_client import exchange_code, get_oauth_url, get_user_login
from interfaces.webapp.dependencies import get_current_user_id, get_database
from shared.config import DOMAIN, YANDEX_OAUTH_CLIENT_ID

router = APIRouter(tags=["oauth"])
logger = logging.getLogger(__name__)

# In-memory state store: state_token → (user_id, created_at)
# Entries expire after 10 minutes
_oauth_states: dict[str, tuple[int, float]] = {}
_STATE_TTL = 600  # 10 minutes


def _cleanup_expired_states() -> None:
    now = time.monotonic()
    expired = [k for k, (_, ts) in _oauth_states.items() if now - ts > _STATE_TTL]
    for k in expired:
        del _oauth_states[k]


def _get_callback_url(request: Request) -> str:
    """Build the OAuth callback URL from DOMAIN env var or request host."""
    if DOMAIN:
        return f"https://{DOMAIN}/api/v1/oauth/yandex/callback"
    # Fallback: derive from request
    return str(request.url_for("yandex_oauth_callback"))


@router.get("/oauth/yandex/url")
async def get_yandex_oauth_url(
    request: Request,
    user_id: int = Depends(get_current_user_id),
) -> dict:
    if not YANDEX_OAUTH_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Yandex OAuth is not configured")

    _cleanup_expired_states()

    state = uuid.uuid4().hex[:16]
    _oauth_states[state] = (user_id, time.monotonic())

    redirect_uri = _get_callback_url(request)
    url = get_oauth_url(state, redirect_uri)
    logger.info("OAuth URL generated for user_id=%d", user_id)
    return {"url": url, "state": state}


@router.get("/oauth/yandex/callback", name="yandex_oauth_callback")
async def yandex_oauth_callback(
    request: Request,
    code: str = "",
    state: str = "",
    db: Database = Depends(get_database),
) -> HTMLResponse:
    """Handle Yandex OAuth redirect. Exchanges code for token and closes the browser tab."""

    def _error_page(msg: str) -> HTMLResponse:
        return HTMLResponse(
            f"<html><body><h3>{msg}</h3><p>You can close this tab.</p></body></html>",
            status_code=400,
        )

    if not code or not state:
        return _error_page("Missing code or state parameter.")

    _cleanup_expired_states()
    entry = _oauth_states.pop(state, None)
    if not entry:
        return _error_page("Invalid or expired OAuth state. Please try again from the app.")

    user_id, _ = entry

    redirect_uri = _get_callback_url(request)
    token = await exchange_code(code, redirect_uri)
    if not token:
        return _error_page("Failed to exchange OAuth code. Please try again.")

    login = await get_user_login(token.access_token)
    await db.set_oauth_token(
        user_id,
        "yandex",
        access_token=token.access_token,
        refresh_token=token.refresh_token,
        expires_at=token.expires_at,
        meta={"login": login},
    )
    logger.info("Yandex OAuth connected via callback: user_id=%d login=%s", user_id, login)

    # Return a page that auto-closes the browser tab
    display = f"Connected as {login}" if login else "Connected successfully"
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>OAuth Success</title>
<style>body{{font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#f5f5f5}}
.card{{text-align:center;padding:2rem;background:white;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,.1)}}
h3{{color:#2ea043;margin-bottom:.5rem}}</style></head>
<body><div class="card"><h3>{display}</h3><p>You can close this tab and return to the app.</p></div>
<script>setTimeout(()=>window.close(),1500)</script></body></html>"""
    return HTMLResponse(html)


@router.delete("/oauth/yandex")
async def disconnect_yandex(
    user_id: int = Depends(get_current_user_id),
    db: Database = Depends(get_database),
) -> dict:
    await db.delete_oauth_token(user_id, "yandex")
    logger.info("Yandex OAuth disconnected: user_id=%d", user_id)
    return {"disconnected": True}
