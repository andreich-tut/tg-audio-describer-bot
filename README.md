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

## Bot commands

| Command    | Description                                            |
|------------|--------------------------------------------------------|
| `/start`   | Help and available commands                            |
| `/mode`    | Switch mode: chat / transcribe only / Obsidian note    |
| `/stop`    | Cancel current processing (also works as plain text)   |
| `/clear`   | Clear conversation history                             |
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
BOT_TOKEN=                    # required
LLM_API_KEY=                  # required — OpenRouter key or other provider
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=qwen/qwen3-235b-a22b:free

WHISPER_BACKEND=local         # "local" or "groq"
WHISPER_MODEL=medium          # tiny / small / medium / large-v3 (local only)
WHISPER_DEVICE=cuda           # cuda or cpu (local only)
GROQ_API_KEY=                 # required when WHISPER_BACKEND=groq
HF_TOKEN=                     # required for speaker diarization (YouTube + CLI)

ALLOWED_USERS=                # comma-separated Telegram user IDs (empty = allow all)
DEFAULT_LANGUAGE=ru           # default bot language: "ru" or "en"
SYSTEM_PROMPT=                # optional: override the default system prompt
WARP_DEBUG=0                  # set to 1 to enable Cloudflare WARP verbose logs
ENCRYPTION_KEY=               # recommended: master key for encrypted data (see PERSISTENCE.md)
```

### Docker Data Persistence

**IMPORTANT:** The `start.sh` script mounts `./data:/app/data` to persist the SQLite database and encryption key across container updates.

Without this volume mount, all user data, OAuth tokens, and settings are lost when the container is rebuilt.

See [PERSISTENCE.md](PERSISTENCE.md) for backup strategies and migration guides.

### LLM providers

`LLM_BASE_URL` + `LLM_API_KEY` accept any OpenAI-compatible endpoint:

| Provider   | `LLM_BASE_URL`                      | Notes                             |
|------------|--------------------------------------|-----------------------------------|
| OpenRouter | `https://openrouter.ai/api/v1`       | Default; many free models         |
| Ollama     | `http://localhost:11434/v1`          | Local; set `LLM_API_KEY=ollama`   |
| DashScope  | `https://dashscope.aliyuncs.com/compatible-mode/v1` | Alibaba Cloud |
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

**Option 1 — Local path** (via Yandex.Disk or any sync client):
```
OBSIDIAN_VAULT_PATH=/home/user/YandexDisk/ObsidianVault
OBSIDIAN_INBOX_FOLDER=Inbox
```

**Option 2 — Yandex.Disk WebDAV** (direct cloud upload, no sync client needed):
```
YANDEX_DISK_LOGIN=yourname@yandex.ru
YANDEX_DISK_PASSWORD=your_app_password   # create at id.yandex.ru/security/app-passwords
YANDEX_DISK_PATH=ObsidianVault
OBSIDIAN_INBOX_FOLDER=Inbox
```

WebDAV takes priority if both are set. Notes are saved as `YYYY-MM-DD-title.md` with YAML front-matter.

## Google Docs (optional)

Save voice transcripts to a Google Doc automatically.

1. Create a service account in [Google Cloud Console](https://console.cloud.google.com/) → IAM & Admin → Service Accounts → Create; download the JSON key
2. Enable the Google Docs API in your project
3. Share the target document with the service account email (Editor role)
4. Copy the document ID from the URL: `.../document/d/<ID>/edit`
5. Add to `.env`:
   ```
   GDOCS_CREDENTIALS_FILE=/path/to/service-account.json
   GDOCS_DOCUMENT_ID=your_document_id
   ```

Use `/savedoc` in the bot to toggle saving on/off per user.

## Security

- Set `ALLOWED_USERS` in `.env` to restrict access to specific Telegram IDs
- Find your ID: message [@userinfobot](https://t.me/userinfobot)
- Conversation history is in-memory only — cleared on restart

## Architecture

```
Voice message → download .ogg → STT (local: faster-whisper / cloud: Groq) → text
                                                                              |
                                         chat: text + history → LLM API → reply
                                         transcribe: return text as-is
                                         note: LLM → Markdown → Telegram + vault
```

### Code structure

Modular design using aiogram 3 Routers:

```
bot.py                          # Entrypoint: bot init, router assembly
shared/                         # Cross-cutting: config, i18n, keyboards, utils
application/                    # State management, processing pipelines, rate limiting
infrastructure/                 # DB, external APIs (LLM, Groq, YouTube, Yandex), storage
interfaces/telegram/handlers/   # aiogram Routers: commands, messages, youtube callbacks, settings
locales/
  en.json                       # English translations
  ru.json                       # Russian translations
prompts/                        # System prompt and summary prompt templates (.md files)
```

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
