# Environment Variables Quick Reference

## Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `BOT_TOKEN` | Telegram bot token from @BotFather | `123456789:ABCdefGHIjklMNOpqrsTUVwxyz` |
| `LLM_API_KEY` | API key for LLM provider (OpenRouter, etc.) | `sk-or-v1-...` |
| `ENCRYPTION_KEY` | Master key for encrypting sensitive data | `NFhUdzZZQS1...` (Base64, 44 chars) |

## Required for Docker Deployment

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIS_URL` | Redis connection for pub/sub | `redis://redis:6379/0` |
| `DOMAIN` | Public domain for OAuth callbacks | `yourdomain.com` |
| `WEBAPP_URL` | TMA public URL | `https://yourdomain.com/tma` |

## Optional Variables (with defaults)

| Variable | Description | Default |
|----------|-------------|---------|
| `ALLOWED_USERS` | Comma-separated user IDs (empty = all) | `` |
| `LLM_BASE_URL` | OpenAI-compatible API endpoint | `https://openrouter.ai/api/v1` |
| `LLM_MODEL` | Model identifier | `qwen/qwen3-235b-a22b:free` |
| `WHISPER_BACKEND` | STT backend: `local` or `groq` | `local` |
| `WHISPER_MODEL` | Whisper model (local only) | `medium` |
| `WHISPER_DEVICE` | Compute device (local only) | `cuda` |
| `GROQ_API_KEY` | Groq API key (if using Groq STT) | `` |
| `DEFAULT_LANGUAGE` | Bot UI language: `ru` or `en` | `ru` |
| `REDIS_URL` | Redis URL (local dev) | `redis://localhost:6379/0` |

## Feature-Specific Variables

### Yandex.Disk OAuth (Required for Yandex.Disk access)
```env
YANDEX_OAUTH_CLIENT_ID=your_client_id
YANDEX_OAUTH_CLIENT_SECRET=your_client_secret
YANDEX_DISK_PATH=Apps/telegram-bot
```

### Google Docs (Optional)
```env
GDOCS_CREDENTIALS_FILE=/path/to/service-account-key.json
GDOCS_DOCUMENT_ID=document_id_from_url
```

### Obsidian (Optional - local or WebDAV)
```env
OBSIDIAN_VAULT_PATH=/path/to/vault
OBSIDIAN_INBOX_FOLDER=Inbox
```

### YouTube (Optional)
```env
YT_MAX_DURATION=7200
YT_COOKIES_FILE=/path/to/cookies.txt
```

### HuggingFace (Optional - for diarization)
```env
HF_TOKEN=hf_your_token
```

## Generating Values

### ENCRYPTION_KEY
```bash
python -c "from infrastructure.database.encryption import generate_key; print(generate_key())"
```

### ALLOWED_USERS
Find your Telegram user ID: send a message to @userinfobot

## Docker vs Local

| Variable | Docker Value | Local Value |
|----------|--------------|-------------|
| `REDIS_URL` | `redis://redis:6379/0` | `redis://localhost:6379/0` |
| `WEBAPP_URL` | `https://domain.com/tma` | `http://localhost:3000` |
| `DOMAIN` | `yourdomain.com` | `localhost` |

## Notes

1. **REDIS_URL**: Auto-configured in `docker-compose.yml` for the bot service
2. **WEBAPP_URL**: Leave empty to disable TMA features (bot falls back to inline menus)
3. **ENCRYPTION_KEY**: If not set, auto-generated key stored in `data/master.key` (backup this!)
4. **ALLOWED_USERS**: Empty = allow all users. Comma-separated numeric IDs only.
