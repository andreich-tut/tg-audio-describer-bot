# Data Persistence

## Overview

The bot uses **SQLite with column-level encryption** for persistent storage. All sensitive data (OAuth tokens, API keys) is encrypted using Fernet (AES-128-CBC + HMAC) before being stored in the database.

---

## Storage Location

**Database file:** `data/bot.db`

**Encryption key:** `data/master.key` (auto-generated if `ENCRYPTION_KEY` not set in env)

**Full path:** `<project_root>/data/`

**Permissions:** 
- Database: `0o644` (read/write for owner, read for others)
- Master key: `0o600` (read/write for owner only)

---

## Docker Persistence

**IMPORTANT:** When running in Docker, you MUST mount the `data/` directory as a volume to persist data across container updates.

### Option 1: Bind Mount (Recommended)

```bash
docker run -d \
  --name tg-voice \
  --env-file .env \
  -v ./data:/app/data \      # ← Mount data directory
  --restart unless-stopped \
  tg-voice:latest
```

**Backup:** Simply copy the `./data/` directory on the host.

### Option 2: Named Volume

```bash
docker run -d \
  --name tg-voice \
  --env-file .env \
  -v voice-bot-data:/app/data \  # ← Named volume
  --restart unless-stopped \
  tg-voice:latest
```

**Backup:** Use `docker run --rm -v voice-bot-data:/data -v $(pwd):/backup alpine tar czf /backup/data-backup.tar.gz /data`

### start.sh Configuration

The included `start.sh` script already includes the bind mount:

```bash
-v ./data:/app/data \
```

**Without this mount, all data is lost when the container is removed!**

---

## Database Schema

```sql
-- Users table (core profile)
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    language TEXT DEFAULT 'ru',
    mode TEXT DEFAULT 'chat',
    is_allowed BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Key-value settings (flexible, extensible)
CREATE TABLE user_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,  -- JSON-encoded or plain text
    is_encrypted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    UNIQUE(user_id, key)
);

-- OAuth tokens (encrypted)
CREATE TABLE oauth_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    provider TEXT NOT NULL,  -- 'yandex', 'google', etc.
    access_token TEXT NOT NULL,  -- encrypted
    refresh_token TEXT,  -- encrypted
    expires_at TIMESTAMP,
    token_meta TEXT,  -- JSON: login, email, etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    UNIQUE(user_id, provider)
);

-- Conversation history (with TTL)
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL,  -- 'user' or 'assistant'
    content TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Free-tier usage tracking
CREATE TABLE free_uses (
    user_id INTEGER PRIMARY KEY,
    count INTEGER DEFAULT 0,
    reset_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
```

---

## Encryption

### Algorithm: Fernet (Symmetric Encryption)

- **Cipher:** AES-128-CBC
- **Authentication:** HMAC-SHA256
- **Key size:** 256-bit (128-bit for encryption + 128-bit for signing)
- **Mode:** Symmetric (same key for encrypt/decrypt)

### Key Management

1. **Environment variable:** Set `ENCRYPTION_KEY` in `.env` (base64-encoded)
2. **Auto-generated:** If not set, key is generated and stored in `data/master.key`
3. **Key rotation:** Generate new key with:
   ```bash
   python -c "from db.encryption import generate_key; print(generate_key())"
   ```

### What's Encrypted

| Data Type | Encrypted? | Reason |
|-----------|-----------|--------|
| OAuth tokens | ✅ Yes | Sensitive authentication credentials |
| API keys (LLM, etc.) | ✅ Yes | Sensitive authentication credentials |
| User settings | ❌ No | Non-sensitive preferences (language, mode) |
| Conversation history | ❌ No | User content (can be encrypted if needed) |
| Free-tier counters | ❌ No | Non-sensitive usage data |

---

## Implementation

### Module: `db/`

| File | Purpose |
|------|---------|
| `db/__init__.py` | Package exports |
| `db/models.py` | SQLAlchemy ORM models |
| `db/database.py` | Database service with CRUD operations |
| `db/encryption.py` | Fernet encryption/decryption utilities |

### Module: `state.py`

Provides backward-compatible API for legacy code:

| Function | Async Version | Purpose |
|----------|--------------|---------|
| `get_user_setting()` | `get_user_setting_async()` | Get string setting |
| `set_user_setting()` | `set_user_setting_async()` | Set string setting |
| `get_user_setting_json()` | `get_user_setting_json_async()` | Get dict setting |
| `set_user_setting_json()` | `set_user_setting_json_async()` | Set dict setting |
| `clear_user_setting()` | `clear_user_setting_async()` | Remove single key |
| `clear_user_settings_section()` | `clear_user_settings_section_async()` | Remove multiple keys |
| `get_oauth_token_async()` | — | Get OAuth tokens |
| `set_oauth_token_async()` | — | Set OAuth tokens |
| `delete_oauth_token_async()` | — | Delete OAuth tokens |
| `add_to_history_async()` | — | Add conversation message |
| `get_history_async()` | — | Get conversation history |
| `clear_history_async()` | — | Clear conversation history |
| `get_free_uses_async()` | — | Get free uses count |
| `set_free_uses_async()` | — | Set free uses count |
| `increment_free_uses_async()` | — | Increment free uses |

### Usage Examples

```python
# Sync (legacy compatibility)
from state import get_user_setting, set_user_setting

api_key = get_user_setting(user_id, "llm_api_key")
set_user_setting(user_id, "language", "ru")

# Async (recommended for new code)
from state import get_user_setting_async, set_user_setting_async

api_key = await get_user_setting_async(user_id, "llm_api_key")
await set_user_setting_async(user_id, "language", "ru")

# OAuth tokens (always async)
from state import set_oauth_token_async, get_oauth_token_async, delete_oauth_token_async

await set_oauth_token_async(
    user_id,
    "yandex",
    access_token="y0_AgAAAA...",
    refresh_token="1_1234567890abcdef...",
    expires_at=datetime(2024, 12, 31),
    meta={"login": "user@yandex.ru"}
)

token = await get_oauth_token_async(user_id, "yandex")
await delete_oauth_token_async(user_id, "yandex")

# Conversation history
from state import add_to_history_async, get_history_async, clear_history_async

await add_to_history_async(user_id, "user", "Hello!")
await add_to_history_async(user_id, "assistant", "Hi there!")

history = await get_history_async(user_id)  # Last MAX_HISTORY messages
await clear_history_async(user_id)
```

---

## Migrations

### Alembic Configuration

**Config file:** `alembic.ini`

**Migration scripts:** `alembic/versions/`

### Create New Migration

```bash
# Generate new migration
venv/bin/alembic revision --autogenerate -m "Description of changes"

# Apply all migrations
venv/bin/alembic upgrade head

# Rollback one migration
venv/bin/alembic downgrade -1

# View migration history
venv/bin/alembic history
```

### Migration History

| Revision | Description | Date |
|----------|-------------|------|
| `001_initial` | Initial schema (users, settings, oauth_tokens, conversations, free_uses) | 2024-01-01 |

---

## Legacy JSON Migration

On first startup, the bot automatically migrates data from `data/user_settings.json` to SQLite:

1. Reads legacy JSON file
2. Creates/updates users in SQLite
3. Migrates settings (encrypts sensitive fields)
4. Migrates OAuth tokens to `oauth_tokens` table
5. Migrates free_uses counters
6. Archives JSON file to `data/user_settings.json.archived`

**Manual migration check:**
```python
from state import migrate_legacy_data
import asyncio
asyncio.run(migrate_legacy_data())
```

---

## Backup & Restore

### Backup Database

```bash
# Simple file copy (bot must be stopped or use WAL mode)
cp data/bot.db data/bot.db.backup.$(date +%Y%m%d)

# Or use SQLite backup command
sqlite3 data/bot.db ".backup 'data/bot.db.backup.$(date +%Y%m%d)'"
```

### Restore Database

```bash
# Stop bot first
cp data/bot.db.backup.YYYYMMDD data/bot.db
```

### Backup Encryption Key

**CRITICAL:** Back up `data/master.key` separately from the database!

```bash
# Backup master key
cp data/master.key /secure/location/master.key.backup

# Or store ENCRYPTION_KEY in password manager
python -c "import base64; print(base64.urlsafe_b64encode(open('data/master.key', 'rb').read()).decode())"
```

**Without the master key, encrypted data is permanently lost!**

---

## Security Considerations

| Risk | Mitigation |
|------|------------|
| Master key theft | Store in env var or secure vault, not in repo |
| Database theft | Encrypted columns protect sensitive data |
| Key loss | Backup master key separately from database |
| Memory exposure | Keys loaded once at startup, not stored in logs |
| SQL injection | SQLAlchemy ORM with parameterized queries |

### Recommendations

1. **Set `ENCRYPTION_KEY` in env:** Don't rely on auto-generated key file
2. **Backup separately:** Database + master key in different locations
3. **Use WAL mode:** For better concurrency (add `?journal_mode=WAL` to DB URL)
4. **Monitor disk space:** SQLite files can grow indefinitely
5. **Rotate keys periodically:** Especially for production deployments

---

## Troubleshooting

### Database Locked

```bash
# Check for zombie processes
lsof data/bot.db

# Kill process or wait for timeout
# SQLite lock timeout: 5 seconds default
```

### Encryption Key Lost

If `data/master.key` is deleted and `ENCRYPTION_KEY` not set:
- Bot will generate new key
- **All encrypted data becomes unreadable**
- Recovery: Only possible if you have backup of master key

### Migration Failed

```bash
# Check Alembic version
venv/bin/alembic current

# Force downgrade/upgrade
venv/bin/alembic downgrade base
venv/bin/alembic upgrade head
```

### Corrupted Database

```bash
# Check integrity
sqlite3 data/bot.db "PRAGMA integrity_check;"

# Try to dump and restore
sqlite3 data/bot.db ".dump" | sqlite3 data/bot.db.recovered
```

---

## Performance

### Connection Pooling

- Default: Single connection (SQLite is serverless)
- For high concurrency: Consider PostgreSQL instead

### Indexes

| Table | Index | Purpose |
|-------|-------|---------|
| `user_settings` | `idx_user_settings_user_id` | Fast lookup by user |
| `oauth_tokens` | `idx_oauth_tokens_user_id` | Fast lookup by user |
| `conversations` | `idx_conversations_user_timestamp` | Ordered history retrieval |

### Optimization Tips

1. **Batch inserts:** Use `executemany()` for bulk operations
2. **WAL mode:** Better concurrent read/write performance
3. **Trim history:** Automatically limited to `MAX_HISTORY` entries
4. **Close sessions:** Always use async context managers

---

## Related Files

| File | Purpose |
|------|---------|
| `db/` | Database package (models, encryption, CRUD) |
| `state.py` | Backward-compatible state API |
| `alembic/` | Database migrations |
| `alembic.ini` | Alembic configuration |
| `services/obsidian.py` | Uses OAuth tokens for Yandex.Disk |
| `services/yandex_oauth.py` | OAuth token management |
| `handlers/settings.py` | User settings UI |
| `handlers/commands.py` | OAuth callback handler |
