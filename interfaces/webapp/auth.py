"""
Telegram Mini App initData HMAC-SHA256 validation.
"""

import hashlib
import hmac
import json
import logging
import os
from urllib.parse import parse_qsl, unquote

from fastapi import HTTPException

logger = logging.getLogger(__name__)


def validate_init_data(init_data: str, bot_token: str) -> dict:
    """
    Validate Telegram WebApp initData and return parsed user dict.
    Raises HTTPException(401) if invalid.

    In development mode (WEBAPP_DEV_MODE=true), accepts mock initData for local testing.
    """
    dev_mode = os.getenv("WEBAPP_DEV_MODE", "").lower() == "true"

    if not init_data:
        if dev_mode:
            logger.warning("Dev mode: Using mock user data (no initData provided)")
            return {"id": 123456789, "username": "dev_user", "first_name": "Dev User"}
        raise HTTPException(status_code=401, detail="Missing X-Telegram-Init-Data header")

    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    hash_to_check = parsed.pop("hash", None)

    if not hash_to_check:
        if dev_mode:
            logger.warning("Dev mode: Skipping hash validation (no hash in initData)")
            user_raw = parsed.get("user", "")
            try:
                user_data = json.loads(unquote(user_raw)) if user_raw else {}
                if not user_data.get("id"):
                    return {"id": 123456789, "username": "dev_user", "first_name": "Dev User"}
                return user_data
            except (json.JSONDecodeError, ValueError):
                return {"id": 123456789, "username": "dev_user", "first_name": "Dev User"}
        raise HTTPException(status_code=401, detail="Missing hash in initData")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))

    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_hash, hash_to_check):
        if dev_mode:
            logger.warning("Dev mode: Skipping HMAC validation (invalid signature)")
            user_raw = parsed.get("user", "{}")
            try:
                return json.loads(unquote(user_raw))
            except (json.JSONDecodeError, ValueError):
                return {"id": 123456789, "username": "dev_user"}
        raise HTTPException(status_code=401, detail="Invalid initData signature")

    user_raw = parsed.get("user", "{}")
    try:
        return json.loads(unquote(user_raw))
    except (json.JSONDecodeError, ValueError) as exc:
        if dev_mode:
            logger.warning("Dev mode: Using mock user data (parse error: %s)", exc)
            return {"id": 123456789, "username": "dev_user"}
        raise HTTPException(status_code=401, detail="Invalid user field in initData") from exc
