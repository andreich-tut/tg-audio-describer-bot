# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Telegram Voice/Audio Bot**: A Telegram bot that processes voice messages, audio files, and YouTube links via Whisper STT and generates responses using any OpenAI-compatible LLM API (default: OpenRouter).

- **Stack**: Python 3.11+, aiogram 3, faster-whisper (local) or Groq (cloud) for STT, OpenAI SDK for LLM
- **Architecture**: Async event-driven (asyncio), SQLite database with encryption for persistence, Docker deployment with Cloudflare WARP
- **Language**: Bilingual UI (Russian/English), per-user language setting
- **Persistence**: SQLite database (`data/bot.db`) with Fernet-encrypted sensitive data (OAuth tokens, API keys)

## Architecture & Key Concepts

### Data Flow
```
User sends voice/audio → bot downloads file → Whisper transcribes (local GPU or Groq cloud) →
  Mode: chat       → LLM processes with conversation context → response sent back
  Mode: transcribe → raw transcript sent back
  Mode: note       → LLM formats as Obsidian note → .md file sent back
```

### Project Structure
```
bot.py              — Entrypoint: creates Bot/Dispatcher, registers routers, starts polling
shared/
  config.py         — Env loading, constants, logging (rotating file + console), access control
  i18n.py           — Internationalization: t(), get_user_locale(), detect_language_from_telegram()
  keyboards.py      — Inline keyboard builders (mode, language, YouTube summary, stop)
  utils.py          — Utilities: audio_suffix, escape_md, run_as_cancellable, get_audio_from_msg
  version.py        — Reads __version__ from pyproject.toml
application/
  state.py          — Database-backed state: SQLite with encryption, full async API
  pipelines.py      — Main processing: process_audio(), process_youtube(), process_text()
  services/
    rate_limiter.py — Rate limit checking: OpenRouter key info + cached Groq headers
infrastructure/
  database/
    models.py       — SQLAlchemy ORM models (users, settings, oauth_tokens, conversations, free_uses)
    database.py     — Async database service with CRUD operations
    encryption.py   — Fernet encryption for sensitive data (OAuth tokens, API keys)
  external_api/
    groq_client.py  — Groq cloud STT (Whisper via API)
    llm_client.py   — LLM chat (OpenAI SDK): ask_ollama(), summarize_ollama(), format_note_ollama()
    youtube.py      — YouTube audio download (yt-dlp), optional whisperX diarization
    yandex_client.py — Yandex OAuth 2.0 flow for Yandex.Disk access
  storage/
    obsidian.py     — Obsidian note saving: local vault or Yandex.Disk WebDAV (OAuth)
    gdocs.py        — Google Docs integration (optional)
interfaces/telegram/
  handlers/
    commands.py     — All /command handlers + inline callback query handlers (mode, lang, cancel, OAuth)
    messages.py     — Message type handlers: voice, audio, video_note, document, video, text
    youtube_callbacks.py — YouTube summary detail-level inline button handlers
    settings.py     — /settings command, per-user API credentials, OAuth login
alembic/
  env.py            — Alembic migration environment
  versions/         — Migration scripts
prompts/
  system.md         — Main chat system prompt
  summary_brief.md  — Brief YouTube summary prompt
  summary_detailed.md — Detailed YouTube summary prompt
  summary_keypoints.md — Keypoints extraction prompt
  note.md           — Obsidian note formatting prompt
locales/
  ru.json           — Russian UI strings
  en.json           — English UI strings
tools/
  audio_splitter.py — FFmpeg-based audio chunking (by size or time)
  transcribe_diarize.py — whisperX + pyannote diarization CLI
  transcribe_cli.py — CLI transcription wrapper (uses Groq STT)
  diarize_all.py    — Batch diarize test/chunks/ → test/source.txt
  send_chunks.py    — Split audio + send chunks to bot via Telegram API
  split.sh          — Shell helper for audio splitting
docker/
  Dockerfile        — Docker image definition
  docker-entrypoint.sh — Container startup: Cloudflare WARP init → python bot.py
  start.sh          — Build image + run container
  update.sh         — Rebuild + prune old images
docs/               — Design docs and migration notes (not part of runtime)
```

## Configuration

All config via `.env` file (template in `.env.example`):
```
BOT_TOKEN=<Telegram bot token>
ALLOWED_USERS=                    # Comma-separated user IDs (empty = all)

# LLM — any OpenAI-compatible API
LLM_API_KEY=
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=qwen/qwen3-235b-a22b:free

# STT
WHISPER_BACKEND=local             # "local" (faster-whisper) or "groq" (cloud)
WHISPER_MODEL=medium              # For local: tiny/small/medium/large-v3
WHISPER_DEVICE=cuda               # For local: cuda or cpu
GROQ_API_KEY=                     # Required when WHISPER_BACKEND=groq

# System prompt
SYSTEM_PROMPT=prompts/system.md

# Google Docs (optional)
GDOCS_CREDENTIALS_FILE=
GDOCS_DOCUMENT_ID=

# Obsidian (optional)
OBSIDIAN_VAULT_PATH=
OBSIDIAN_INBOX_FOLDER=Inbox
YANDEX_DISK_PATH=ObsidianVault

# Yandex OAuth (REQUIRED for Yandex.Disk access)
YANDEX_OAUTH_CLIENT_ID=           # Create at https://oauth.yandex.ru/client/new
YANDEX_OAUTH_CLIENT_SECRET=       # Required scopes: login:info, cloud_api:disk.app_folder
                                  # Redirect URI: https://t.me/<your_bot_username>

# YouTube
YT_MAX_DURATION=7200
YT_COOKIES_FILE=

# Internationalization
DEFAULT_LANGUAGE=ru

# Database Encryption (REQUIRED for production)
ENCRYPTION_KEY=                   # Generate: python -c "from infrastructure.database.encryption import generate_key; print(generate_key())"
                                  # If not set, auto-generated and stored in data/master.key
```

## Development & Running

### Setup
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt          # Cloud-only (Groq STT + OpenRouter LLM)
pip install -r requirements-local.txt    # Adds faster-whisper for local STT
cp .env.example .env
# Edit .env: add BOT_TOKEN, LLM_API_KEY, ENCRYPTION_KEY, etc.
```

### Prerequisites
- **LLM API**: Any OpenAI-compatible endpoint (OpenRouter, local vLLM, etc.) with API key
- **STT**: Either Groq API key (`WHISPER_BACKEND=groq`) or local faster-whisper with CUDA GPU (`WHISPER_BACKEND=local`)
- **Telegram Bot Token**: From @BotFather
- **Yandex OAuth** (for Yandex.Disk): Client ID + Secret from oauth.yandex.ru

### Run Locally
```bash
python bot.py
```

### Run with Docker
```bash
./docker/start.sh    # Builds Docker image + runs with Cloudflare WARP
./docker/update.sh   # Rebuilds + prunes old images
```

**Data persistence:** `./data` directory is automatically created and mounted as volume.

### CI/CD
- `.github/workflows/pylint.yml` — Runs pylint on every push
- `.github/workflows/deploy.yml` — On push to main (or manual): lint → SSH deploy to VPS

### Linting
- **Ruff** via pre-commit hooks (`.pre-commit-config.yaml`): lint + format, line-length 120
- **Pylint** via `.pylintrc`
- Auto version bump: `.githooks/bump-version.sh` increments patch version in `pyproject.toml` on each commit

### Debugging
- Logs: rotating files in `logs/` directory + console output (level=INFO)
- `/ping` command tests LLM API connectivity
- `/limits` shows OpenRouter + Groq rate limit usage
- Conversation history: persisted in SQLite database

## Bot Commands
| Command | Handler | Notes |
|---------|---------|-------|
| `/start` | `cmd_start()` | Shows help, version, and available commands |
| `/mode` | `cmd_mode()` | Inline keyboard to switch: chat / transcribe / note |
| `/stop` | `cmd_stop()` | Cancel active processing task (also: "stop" / "стоп" text) |
| `/clear` | `cmd_clear()` | Clears user's conversation history |
| `/model` | `cmd_model()` | Shows current LLM_MODEL and WHISPER_MODEL |
| `/ping` | `cmd_ping()` | Tests LLM API connection |
| `/limits` | `cmd_limits()` | Shows OpenRouter + Groq free-tier usage |
| `/lang` | `cmd_lang()` | Inline keyboard to switch UI language (ru/en) |
| `/savedoc` | `cmd_savedoc()` | Toggle Google Docs saving (opt-in) |
| `/settings` | `cmd_settings()` | Personal API credentials and storage settings |

Voice, audio, and text message handlers check `is_allowed()` before processing.

## Common Tasks

### Change LLM Model
Edit `.env`: `LLM_MODEL=anthropic/claude-3.5-sonnet` (or any model on your API provider)

### Change STT Backend
Edit `.env`: `WHISPER_BACKEND=groq` (cloud, needs `GROQ_API_KEY`) or `WHISPER_BACKEND=local` (needs `requirements-local.txt` + GPU)

### Change Whisper Model (local STT only)
Edit `.env`: `WHISPER_MODEL=large-v3` (better quality, slower) or `tiny` (faster, lower quality)
- GPU VRAM: tiny ~1GB, small ~2GB, medium ~5GB, large-v3 ~10GB

### Customize System Prompt
Edit `SYSTEM_PROMPT=` in `.env` to point to a different `.md` file

### Restrict Access
Edit `.env`: `ALLOWED_USERS=123456789,987654321` (comma-separated Telegram user IDs)

### Change UI Language
Default set via `DEFAULT_LANGUAGE=ru` in `.env`. Users can switch per-session with `/lang`.

### Yandex.Disk OAuth Setup
1. Go to https://oauth.yandex.ru/client/new
2. Create new OAuth application
3. Set scopes: `login:info`, `cloud_api:disk.app_folder`
4. Platform: Web services
5. Redirect URI: `https://t.me/<your_bot_username>`
6. Copy Client ID and Secret to `.env`

## Code Notes

- **Conversation history**: Trimmed to last MAX_HISTORY (20) pairs to avoid context overflow
- **Message splitting**: Responses >4000 chars split into multiple Telegram messages
- **Async**: Uses asyncio + aiogram for non-blocking I/O
- **Cancellation**: Active tasks stored in `application.state.active_tasks`, cancellable via `/stop`
- **Rate limiting**: LLM calls retry with exponential backoff (5s/15s/30s) on RateLimitError
- **Error handling**: Exceptions logged and user notified in chat
- **Persistence**: SQLite database with encryption (data persists across restarts)
- **i18n**: All UI strings in `locales/{ru,en}.json`, accessed via `shared.i18n.t(key, locale)`

## Dependencies
- `aiogram>=3.10` — Telegram bot framework (async)
- `python-dotenv>=1.0` — Load .env config
- `httpx>=0.27` — Async HTTP client (Groq STT, limits checking)
- `openai>=1.0` — OpenAI-compatible LLM client
- `yt-dlp>=2024.0` — YouTube audio download
- `google-api-python-client>=2.100` / `google-auth>=2.23` — Google Docs integration
- `pre-commit>=3.0` — Git hooks
- `faster-whisper>=1.0` — Local GPU-accelerated STT (optional, in `requirements-local.txt`)
- `sqlalchemy[asyncio]>=2.0` — Async ORM for SQLite
- `aiosqlite>=0.19` — Async SQLite driver
- `alembic>=1.13` — Database migrations
- `cryptography>=41.0` — Fernet encryption for sensitive data
