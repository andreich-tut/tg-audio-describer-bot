# Telegram Voice → LLM Bot

Local Telegram bot: voice messages → faster-whisper (STT) → LLM (OpenRouter / any OpenAI-compatible API) → text reply.

## Requirements

- Python 3.11+ (or Docker)
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- LLM API key: [OpenRouter](https://openrouter.ai/keys) (has free models) or any OpenAI-compatible provider
- STT — choose one:
  - **Local**: NVIDIA GPU with CUDA + faster-whisper (or CPU, slower)
  - **Cloud**: free [Groq](https://console.groq.com) API key (no GPU needed)

## Quick start

### Docker (recommended)

```bash
cp .env.example .env
# Fill in BOT_TOKEN and LLM_API_KEY at minimum
./start.sh
```

Logs: `docker logs -f tg-voice`

**Data persistence:** The `./data` directory is automatically created and mounted to persist the SQLite database and encryption key across container updates.

### Python

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements-local.txt   # includes faster-whisper
# or: pip install -r requirements.txt   # without local STT
cp .env.example .env
# Fill in BOT_TOKEN and LLM_API_KEY
python bot.py
```

**Data persistence:** Data stored in `data/bot.db` (SQLite) with encryption key in `data/master.key`.

## Development

After cloning, install pre-commit hooks (runs ruff lint, ruff format, and auto-bumps patch version on each commit):

```bash
pip install pre-commit
pre-commit install
```

### LLM Skills Setup

Set up symlinks for AI assistant skills (Claude Code, Qwen Code):

```bash
mkdir -p .claude .qwen
ln -s $(pwd)/skills .claude/skills
ln -s $(pwd)/skills .qwen/skills
```

## Bot commands

| Command    | Description                                            |
|------------|--------------------------------------------------------|
| `/start`   | Help and available commands                            |
| `/mode`    | Switch mode: chat / transcribe only / Obsidian note    |
| `/stop`    | Cancel current processing (also works as plain text)   |
| `/model`   | Show current LLM and Whisper models                    |
| `/ping`    | Check LLM API availability                             |
| `/limits`  | Show free-tier API usage (OpenRouter, Groq)            |
| `/savedoc` | Toggle saving transcripts to Google Docs               |
| `/lang`    | Change bot language (en / ru)                          |

## Usage

1. Send a voice message — the bot transcribes and responds
2. Send plain text — the bot responds via LLM
3. Send a YouTube link — get a transcript file + summarization with selectable detail levels
   - Add the word "speakers" / "спикеры" to enable speaker diarization
4. Reply to a voice/audio message with text — processes that audio

### Modes (`/mode`)

| Mode              | Behavior                                                                    |
|-------------------|-----------------------------------------------------------------------------|
| Chat (default)    | Voice → transcribe → LLM → reply                                           |
| Transcribe only   | Voice → transcribe → return raw text, no LLM                               |
| Obsidian note     | Voice → LLM → structured Markdown note; auto-saved to vault if configured  |

## Configuration

All settings via `.env` (template: `.env.example`):

```
# ──────────────────────────────────────────────
# Telegram
# ──────────────────────────────────────────────
BOT_TOKEN=                    # required
ALLOWED_USERS=                # comma-separated Telegram user IDs (empty = allow all)

# ──────────────────────────────────────────────
# LLM (OpenRouter or any OpenAI-compatible API)
# ──────────────────────────────────────────────
LLM_API_KEY=                  # required — OpenRouter key or other provider
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=                    # e.g., nvidia/nemotron-3-super-120b-a12b:free

# ──────────────────────────────────────────────
# Whisper (STT)
# ──────────────────────────────────────────────
WHISPER_BACKEND=local         # "local" (faster-whisper) or "groq" (cloud)
WHISPER_MODEL=large-v3        # tiny / small / medium / large-v3 (local only)
WHISPER_DEVICE=cuda           # cuda or cpu (local only)
GROQ_API_KEY=                 # required when WHISPER_BACKEND=groq

# ──────────────────────────────────────────────
# YouTube transcription
# ──────────────────────────────────────────────
YT_MAX_DURATION=7200          # max video duration in seconds (default: 2 hours)
YT_COOKIES_FILE=              # path to cookies.txt for yt-dlp (if YouTube blocks downloads)
HF_TOKEN=                     # required for speaker diarization (YouTube + CLI)

# ──────────────────────────────────────────────
# Yandex.Disk OAuth (for Obsidian vault sync)
# ──────────────────────────────────────────────
YANDEX_OAUTH_CLIENT_ID=       # OAuth app ID from https://oauth.yandex.ru/client/new
YANDEX_OAUTH_CLIENT_SECRET=   # OAuth app secret
YANDEX_DISK_PATH=             # folder path on Yandex.Disk (e.g., dev/hh-knowledge)

# ──────────────────────────────────────────────
# Obsidian vault (local path alternative)
# ──────────────────────────────────────────────
OBSIDIAN_VAULT_PATH=          # local vault path (e.g., /home/user/YandexDisk/ObsidianVault)
OBSIDIAN_INBOX_FOLDER=Inbox   # subfolder for notes

# ──────────────────────────────────────────────
# System & Security
# ──────────────────────────────────────────────
SYSTEM_PROMPT=prompts/system.md
ENCRYPTION_KEY=               # recommended: master key for encrypted data

# ──────────────────────────────────────────────
# Mini App Web API (docker-compose deployment)
# ──────────────────────────────────────────────
DOMAIN=                       # your domain for Mini App (e.g., anywebstorage.ru)
WEBAPP_URL=                   # public URL for TMA (e.g., https://anywebstorage.ru)
REDIS_URL=redis://localhost:6379/0  # Redis connection for pub/sub (SSE OAuth sync)
```

### Docker Data Persistence

**IMPORTANT:** The `start.sh` script mounts `./data:/app/data` to persist the SQLite database and encryption key across container updates.

Without this volume mount, all user data, OAuth tokens, and settings are lost when the container is rebuilt.

See `obsidian/TG Audio Bot/persistence.md` for backup strategies and migration guides.

### LLM providers

`LLM_BASE_URL` + `LLM_API_KEY` accept any OpenAI-compatible endpoint:

| Provider   | `LLM_BASE_URL`                      | Notes                             |
|------------|--------------------------------------|-----------------------------------|
| OpenRouter | `https://openrouter.ai/api/v1`       | Default; many free models         |
| Ollama     | `http://localhost:11434/v1`          | Local; set `LLM_API_KEY=ollama`   |
| DashScope  | `https://dashscope.aliyuncs.com/compatible-mode/v1` | Alibaba Cloud |
| NVIDIA     | `https://integrate.api.nvidia.com/v1` | NVIDIA NIM models               |
| Any other  | your endpoint                        | Must be OpenAI-compatible         |

### Whisper STT

| Model      | VRAM    | Speed | Quality (RU) |
|------------|---------|-------|--------------|
| `tiny`     | ~1 GB   | +++   | low          |
| `small`    | ~2 GB   | ++    | fair         |
| `medium`   | ~5 GB   | +     | good         |
| `large-v3` | ~10 GB  | slow  | best         |

For cloud STT without a GPU, set `WHISPER_BACKEND=groq` and add `GROQ_API_KEY=` to `.env`.

For YouTube speaker diarization, add `HF_TOKEN=` (free [HuggingFace](https://huggingface.co/settings/tokens) token).

## Obsidian vault (optional)

In note mode, the bot formats voice as a structured Markdown note and can save it automatically.

**Option 1 — Yandex.Disk OAuth** (recommended — no sync client needed):
```
YANDEX_OAUTH_CLIENT_ID=your_oauth_app_id
YANDEX_OAUTH_CLIENT_SECRET=your_oauth_secret
YANDEX_DISK_PATH=dev/hh-knowledge      # folder on Yandex.Disk
OBSIDIAN_INBOX_FOLDER=Inbox
```
Users authenticate via OAuth button in `/settings`. Notes are saved to `disk:/dev/hh-knowledge/Inbox/YYYY-MM-DD-title.md`.

**Option 2 — Local path** (via Yandex.Disk or any sync client):
```
OBSIDIAN_VAULT_PATH=/home/user/YandexDisk/ObsidianVault
OBSIDIAN_INBOX_FOLDER=Inbox
```

Notes are saved as `YYYY-MM-DD-title.md` with YAML front-matter.

## Security

- Set `ALLOWED_USERS` in `.env` to restrict access to specific Telegram IDs
- Find your ID: message [@userinfobot](https://t.me/userinfobot)

## Architecture

```
Voice message → download .ogg → STT (local: faster-whisper / cloud: Groq) → text
                                                                              |
                                         chat: text → LLM API → reply
                                         transcribe: return text as-is
                                         note: LLM → Markdown → Telegram + vault
```

### Code structure

Modular design using aiogram 3 Routers:

```
bot.py                          # Entrypoint: bot init, router assembly
shared/                         # Cross-cutting: config, i18n, keyboards, utils
application/
  state.py                      # Runtime in-memory state + re-exports
  user_settings.py              # Per-user settings CRUD
  free_uses.py / oauth_state.py # Free-use counters, OAuth token state
  pipelines/                    # audio.py, text.py, youtube.py — processing pipelines
  services/rate_limiter.py      # Rate limit checking
infrastructure/
  database/                     # SQLAlchemy models, Database class, repo layer (user/conv/oauth)
  external_api/                 # LLM client + operations, Groq STT, YouTube, Yandex OAuth
  storage/                      # Obsidian (local/WebDAV) and Google Docs
interfaces/telegram/handlers/   # aiogram Routers: commands, diagnostics, messages,
                                #   youtube callbacks, settings + settings_ui/oauth
locales/
  en.json                       # English translations
  ru.json                       # Russian translations
prompts/                        # System prompt and summary prompt templates (.md files)
```

---

## Deployment

### Quick Deploy (Docker)

```bash
cp .env.example .env
# Edit .env: add BOT_TOKEN, LLM_API_KEY, ENCRYPTION_KEY
./scripts/start.sh
```

See [Configuration](#configuration) for all `.env` options.

### VPS Deployment (Full Guide)

For production deployment on a fresh VPS with proper security (fail2ban, UFW firewall, dedicated user):

1. **Server Preparation** — Install Docker, Git, fail2ban, UFW
2. **Create Dedicated User** — Security isolation (`botuser`)
3. **Clone & Configure** — Set up `.env` with encryption key
4. **Deploy with Docker** — Start with automatic restart

**Full guide in Obsidian:** `obsidian/TG Audio Bot/vps-setup-guide.md`

**Quick commands:**
```bash
# Generate encryption key
docker run --rm python:3.9-slim python -c "import secrets; print(secrets.token_urlsafe(32))"

# After setup, view logs
docker logs -f tg-audio

# Backup (stop container first!)
docker stop tg-audio
tar -czvf bot-data-backup-$(date +%Y%m%d).tar.gz ~/tg-audio-describer/data/
docker start tg-audio
```

### Mini App Deployment (HTTPS)

For the web-based settings UI with auto-HTTPS:

```bash
# Requires domain pointing to VPS
echo "DOMAIN=yourdomain.com" >> .env
bash scripts/start.sh  # Includes Caddy reverse proxy
```

Register Mini App with BotFather: `/newapp` → your bot → `https://yourdomain.com`

---

## CLI tools ([tools/](tools/))

Standalone utilities for working with audio files locally. Full docs: [tools/README.md](tools/README.md).

### transcribe_cli.py

Transcribes files using the same Whisper model as the bot.

```bash
python tools/transcribe_cli.py recording.ogg
python tools/transcribe_cli.py lecture.webm -o result.txt
python tools/transcribe_cli.py part1.webm part2.webm part3.webm -o result.txt
```

### transcribe_diarize.py

Transcribes audio and labels speakers using whisperX + pyannote.audio.

```bash
pip install whisperx   # one-time

python tools/transcribe_diarize.py meeting.mp3
python tools/transcribe_diarize.py meeting.mp3 --min-speakers 2 --max-speakers 3 -o transcript.txt
```

Requires `HF_TOKEN` in `.env` (free HuggingFace token). See [tools/README.md](tools/README.md) for setup.

### audio_splitter.py

Splits large audio/video files with ffmpeg.

```bash
python tools/audio_splitter.py lecture.webm --minutes 5
```

### send_chunks.py

Splits a file and sends each chunk to the bot directly via Telegram API. Useful for files over 20 MB.

```bash
python tools/send_chunks.py big_recording.webm 123456789
```

---

## Mini App (Web Settings UI)

The bot includes a web-based settings UI accessible as a Telegram Mini App.

### Quick Setup (5 minutes)

1. **Build frontend**:
   ```bash
   cd webapp && npm install && npm run build
   ```

2. **Configure domain** in `.env`:
   ```
   DOMAIN=yourdomain.com
   WEBAPP_URL=https://yourdomain.com
   REDIS_URL=redis://localhost:6379/0
   ```

3. **Deploy with Docker Compose** (includes Caddy for HTTPS):
   ```bash
   docker-compose up -d
   ```

4. **Set Mini App URL** in bot:
   ```
   /setmenu https://yourdomain.com
   ```

5. **Open bot** → Click "Settings" button in menu

### Features

- Configure LLM API credentials
- Yandex.Disk OAuth integration (users authenticate via button)
- Obsidian vault settings
- Real-time connection status

### Development

```bash
# Run backend API
python app_runner.py

# Run frontend dev server
cd webapp && npm run dev
```

See [docs/miniapp-implementation-plan.md](docs/miniapp-implementation-plan.md) for architecture details.
