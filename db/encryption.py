"""
Encryption module for sensitive data using Fernet (AES-128-CBC + HMAC).

Provides transparent encryption/decryption for:
- OAuth tokens
- API keys
- Passwords
- Other sensitive settings

Key derivation:
- Master key from ENCRYPTION_KEY env var (base64-encoded Fernet key)
- If not set, generates and stores a new key in data/master.key
"""

import base64
import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

_KEY_FILE = Path(__file__).parent.parent / "data" / "master.key"


def _get_or_create_key() -> bytes:
    """Get encryption key from env or create new one."""
    # Check environment variable first
    env_key = os.getenv("ENCRYPTION_KEY")
    if env_key:
        try:
            # Decode base64-encoded key
            return base64.urlsafe_b64decode(env_key)
        except Exception as e:
            logger.warning("Invalid ENCRYPTION_KEY in env: %s. Using key file.", e)

    # Check key file
    if _KEY_FILE.exists():
        try:
            key = _KEY_FILE.read_bytes().strip()
            # Validate it's a proper Fernet key
            Fernet(key)  # Raises if invalid
            return key
        except Exception as e:
            logger.error("Failed to load encryption key from %s: %s", _KEY_FILE, e)

    # Generate new key
    key = Fernet.generate_key()
    _KEY_FILE.parent.mkdir(exist_ok=True)
    _KEY_FILE.write_bytes(key)
    os.chmod(_KEY_FILE, 0o600)
    logger.info("Generated new encryption key: %s", _KEY_FILE)
    logger.warning("ENCRYPTION_KEY not set. Generated key stored in %s", _KEY_FILE)
    logger.warning("Set ENCRYPTION_KEY env var for production: %s", base64.urlsafe_b64encode(key).decode())
    return key


# Global Fernet instance
_master_key = _get_or_create_key()
_fernet = Fernet(_master_key)


def encrypt(value: str) -> str:
    """Encrypt a string value. Returns base64-encoded ciphertext."""
    if not value:
        return value
    token = _fernet.encrypt(value.encode("utf-8"))
    return token.decode("utf-8")


def decrypt(token: str) -> str:
    """Decrypt a base64-encoded ciphertext. Returns original string."""
    if not token:
        return token
    try:
        value = _fernet.decrypt(token.encode("utf-8"))
        return value.decode("utf-8")
    except Exception as e:
        logger.error("Decryption failed: %s", e)
        raise ValueError(f"Failed to decrypt: {e}")


def generate_key() -> str:
    """Generate a new Fernet key (for ENCRYPTION_KEY env var)."""
    return base64.urlsafe_b64encode(Fernet.generate_key()).decode()
