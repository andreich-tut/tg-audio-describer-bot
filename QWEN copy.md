# QWEN.md

This file provides guidance to Qwen Code when working with code in this repository.

## Project Overview

**Telegram Voice/Audio Bot**: A Telegram bot that processes voice messages, audio files, and YouTube links via Whisper STT and generates responses using any OpenAI-compatible LLM API (default: OpenRouter).

- **Stack**: Python 3.11+, aiogram 3, faster-whisper (local) or Groq (cloud) for STT, OpenAI SDK for LLM
- **Architecture**: Async event-driven (asyncio), SQLite database with encryption for persistence, Docker deployment with Caddy HTTPS
- **Language**: Bilingual UI (Russian/English), per-user language setting
- **Persistence**: SQLite database (`data/bot.db`) with Fernet-encrypted sensitive data (OAuth tokens, API keys)
- **Mini App**: Telegram Web App for settings UI (React + Vite frontend, Python SSE backend)

## Architecture

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
app_runner.py       — Mini App backend: SSE events, OAuth sync, API endpoints
shared/
  config.py         — Env loading, constants, logging (rotating file + console), access control
  i18n.py           — Internationalization: t(), get_user_locale(), detect_language_from_telegram()
  keyboards.py      — Inline keyboard builders (mode, language, YouTube summary, stop)
  utils.py          — Utilities: audio_suffix, escape_md, run_as_cancellable, get_audio_from_msg
  version.py        — Reads __version__ from pyproject.toml
application/
  state.py          — Runtime in-memory state + re-exports from sub-modules; initialize_state()
  conversation.py   — Conversation history CRUD (sync + async wrappers)
  user_settings.py  — Per-user settings CRUD (sync + async wrappers)
  free_uses.py      — Free-use counter CRUD (sync + async wrappers)
  oauth_state.py    — OAuth token storage and get_or_create_user()
  migration.py      — Legacy data migration helper
  pipelines/
    __init__.py     — Re-exports process_audio, process_text, process_youtube
    audio.py        — Audio processing pipeline
    text.py         — Text processing pipeline
    youtube.py      — YouTube processing pipeline
  services/
    rate_limiter.py — Rate limit checking: OpenRouter key info + cached Groq headers
infrastructure/
  database/
    models.py       — SQLAlchemy ORM models (users, settings, oauth_tokens, conversations, free_uses)
    database.py     — Async Database class with repo delegation; init_db(), close()
    user_repo.py    — UserRepo: user + settings CRUD
    conversation_repo.py — ConversationRepo: history CRUD
    oauth_repo.py   — OAuthRepo: OAuth token CRUD
    encryption.py   — Fernet encryption for sensitive data (OAuth tokens, API keys)
    migrations/     — SQLAlchemy migration scripts
  external_api/
    groq_client.py  — Groq cloud STT (Whisper via API)
    llm_client.py   — Low-level LLM client: _get_client(), _get_model(), ping_llm(), _chat_with_retry()
    llm_operations.py — High-level LLM ops: ask_ollama(), summarize_ollama(), format_note_ollama()
    youtube.py      — YouTube audio download (yt-dlp), optional whisperX diarization
    yandex_client.py — Yandex OAuth 2.0 flow for Yandex.Disk access
  storage/
    obsidian.py     — Obsidian note saving: local vault or Yandex.Disk WebDAV (OAuth)
interfaces/telegram/
  handlers/
    commands.py     — /start, /mode, /stop, /clear, /model + mode/cancel callbacks
    diagnostics.py  — /ping, /limits, /lang + lang callback
    messages.py     — Message type handlers: voice, audio, video_note, document, video, text
    youtube_callbacks.py — YouTube summary detail-level inline button handlers
    settings.py     — /settings command entry point
    settings_ui.py  — Settings keyboard/text builders, key metadata
    settings_oauth.py — OAuth login/disconnect callbacks for Yandex.Disk
    oauth_callback.py — OAuth deep-link handler: /start oauth_<code>_<state>
  middlewares/      — Request middlewares (i18n, user tracking)
prompts/            — System prompts for LLM (chat, summary, note formatting)
locales/            — UI strings: ru.json, en.json
tools/              — CLI utilities: audio splitting, transcription, diarization
docker/             — Dockerfile, entrypoint, start/update scripts, docker-compose.yml
webapp/             — Mini App: React + Vite frontend, Python SSE backend
docs/               — Design docs and migration notes (not part of runtime)
```

## Code Notes

- **Conversation history**: Trimmed to last MAX_HISTORY (20) pairs to avoid context overflow
- **Message splitting**: Responses >4000 chars split into multiple Telegram messages
- **Async**: Uses asyncio + aiogram for non-blocking I/O
- **Cancellation**: Active tasks stored in `application.state.active_tasks`, cancellable via `/stop`
- **Rate limiting**: LLM calls retry with exponential backoff (5s/15s/30s) on RateLimitError
- **i18n**: All UI strings in `locales/{ru,en}.json`, accessed via `shared.i18n.t(key, locale)`
- **Linting**: Ruff via pre-commit hooks, line-length 120. Pylint via `.pylintrc`.
- **Mini App SSE**: Server-Sent Events for real-time OAuth status sync via Redis pub/sub

See [PROJECT.md](docs/PROJECT.md) for: configuration (.env), setup, running, Docker, CI/CD, bot commands, dependencies.

**Documentation:** User-facing documentation (deployment guides, reference, usage guides) is stored in `../obsidian/TG Audio Bot/` for use in Obsidian.

## Conventions

- **Docs naming**: All markdown files in `docs/` use `kebab-case.md` (e.g. `refactor-plan.md`, not `REFACTOR_PLAN.md`). Exception: `docs/ai-context/PROJECT.md` (well-known root-level name).
- **Dual config files**: Project-wide conventions and rules must be added to both `CLAUDE.md` and `QWEN.md` to keep them in sync.

## Skills

- **Skill recognition**: When user types a `/` command (e.g., `/commit-name`), immediately invoke the `skill` tool with the command name (without the `/`). Do NOT execute the command manually.
- Available skills are in `skills/` directory, symlinked to `.qwen/skills` and `.claude/skills`.

## Qwen Added Memories
- Do not add Co-authored-by lines when suggesting git commit messages
