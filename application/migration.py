"""
Legacy JSON data migration to SQLite.
"""

import json
import logging
from pathlib import Path

from infrastructure.database import get_db

logger = logging.getLogger(__name__)

_JSON_FILE = Path(__file__).parent / "data" / "user_settings.json"


async def migrate_legacy_data() -> bool:
    """Migrate data from legacy JSON file to SQLite.

    Returns True if migration was performed, False if no legacy data found.
    """
    if not _JSON_FILE.exists():
        return False

    try:
        json_data = json.loads(_JSON_FILE.read_text(encoding="utf-8"))
        if not json_data:
            return False

        db = get_db()
        migrated = await db.migrate_from_json(json_data)
        logger.info("Migrated %d users from legacy JSON to SQLite", migrated)

        archive_path = _JSON_FILE.with_suffix(".json.archived")
        _JSON_FILE.rename(archive_path)
        logger.info("Archived legacy JSON file to %s", archive_path)

        return True
    except Exception as e:
        logger.error("Failed to migrate legacy data: %s", e)
        return False
