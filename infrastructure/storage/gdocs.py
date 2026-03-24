"""
Google Docs: optional integration for saving transcriptions.
"""

import asyncio
import logging

from config import GDOCS_CREDENTIALS_FILE, GDOCS_DOCUMENT_ID
from state import user_gdocs

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Init Google Docs (optional)
# ──────────────────────────────────────────────
gdocs_service = None
if GDOCS_CREDENTIALS_FILE and GDOCS_DOCUMENT_ID:
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build as _gdocs_build

        _creds = service_account.Credentials.from_service_account_file(
            GDOCS_CREDENTIALS_FILE,
            scopes=["https://www.googleapis.com/auth/documents"],
        )
        gdocs_service = _gdocs_build("docs", "v1", credentials=_creds)
        logger.info("Google Docs integration enabled. Document ID: %s", GDOCS_DOCUMENT_ID)
    except Exception as e:
        logger.error("Failed to initialize Google Docs: %s. Feature disabled.", e)


def is_gdocs_enabled(user_id: int) -> bool:
    return gdocs_service is not None and user_gdocs.get(user_id, False)


async def save_to_gdocs(user_id: int, username: str | None, text: str) -> None:
    """Append a timestamped transcription entry to the configured Google Doc."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    display = username or str(user_id)
    entry = f"[{now}] @{display}\n{text}\n\n"

    loop = asyncio.get_event_loop()
    try:

        def _append():
            doc = gdocs_service.documents().get(documentId=GDOCS_DOCUMENT_ID).execute()
            end_index = doc["body"]["content"][-1]["endIndex"] - 1
            gdocs_service.documents().batchUpdate(
                documentId=GDOCS_DOCUMENT_ID,
                body={"requests": [{"insertText": {"location": {"index": end_index}, "text": entry}}]},
            ).execute()

        await asyncio.wait_for(loop.run_in_executor(None, _append), timeout=15.0)
        logger.info("Saved transcription to Google Docs for user %d", user_id)
    except Exception as e:
        logger.error("Google Docs save failed for user %d: %s", user_id, e)
