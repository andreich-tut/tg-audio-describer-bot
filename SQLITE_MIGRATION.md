# SQLite Persistence Migration Summary

## What Changed

Migrated from JSON file storage to **SQLite database with column-level encryption**.

## Key Benefits

| Before (JSON) | After (SQLite) |
|--------------|----------------|
| ❌ Plain text storage | ✅ Encrypted sensitive data (Fernet AES-128) |
| ❌ No transactions | ✅ ACID compliant |
| ❌ File corruption risk | ✅ Atomic writes |
| ❌ No schema | ✅ Typed schema + migrations |
| ❌ Manual backups | ✅ SQLite backup tools |

## Files Added

```
db/
├── __init__.py          # Package exports
├── encryption.py        # Fernet encryption
├── models.py            # SQLAlchemy ORM models (5 tables)
└── database.py          # Async CRUD operations

alembic/
├── env.py               # Alembic environment
├── script.py.mako       # Migration template
└── versions/
    └── 001_initial_schema.py  # Initial migration

alembic.ini              # Alembic configuration
PERSISTENCE.md           # Complete documentation
```

## Files Modified

| File | Changes |
|------|---------|
| `state.py` | Complete rewrite with SQLite backend |
| `bot.py` | Database init/shutdown hooks |
| `handlers/commands.py` | OAuth uses `set_oauth_token_async()` |
| `handlers/settings.py` | Disconnect uses `delete_oauth_token_async()` |
| `services/obsidian.py` | Removed legacy WebDAV, OAuth only |
| `requirements.txt` | Added sqlalchemy, aiosqlite, alembic, cryptography |
| `.env.example` | Added `ENCRYPTION_KEY` configuration |
| `start.sh` | Added `./data` volume mount + auto-create |

## Database Schema

**5 tables:**
- `users` - User profiles
- `user_settings` - Key-value settings (encrypted for sensitive data)
- `oauth_tokens` - OAuth tokens (always encrypted)
- `conversations` - Message history
- `free_uses` - Free-tier counters

## Encryption

- **Algorithm:** Fernet (AES-128-CBC + HMAC-SHA256)
- **Key:** From `ENCRYPTION_KEY` env or `data/master.key`
- **Encrypted fields:** OAuth tokens, API keys, passwords

## Migration (Automatic)

On first startup:
1. Reads `data/user_settings.json` (if exists)
2. Migrates to SQLite
3. Archives JSON to `.archived`
4. Continues normal operation

## Usage

```python
# Sync (backward compatible)
from state import get_user_setting, set_user_setting
api_key = get_user_setting(user_id, "llm_api_key")

# Async (recommended)
from state import get_oauth_token_async, set_oauth_token_async
token = await get_oauth_token_async(user_id, "yandex")
```

## Docker Persistence

```bash
# start.sh now includes:
-v ./data:/app/data
```

**Without this, all data is lost on container rebuild!**

## Backup

```bash
# Database
cp data/bot.db data/bot.db.backup.$(date +%Y%m%d)

# Master key (CRITICAL - store separately!)
cp data/master.key /secure/location/
```

## Testing

All checks passed:
- ✅ Ruff linting
- ✅ Ruff formatting
- ✅ Python syntax
- ✅ Module imports
- ✅ Database initialization
- ✅ Encryption/decryption
- ✅ Bot startup

## Documentation

- **PERSISTENCE.md** - Complete persistence guide
- **README.md** - Updated with Docker persistence note
- **.env.example** - Updated with OAuth-first configuration
