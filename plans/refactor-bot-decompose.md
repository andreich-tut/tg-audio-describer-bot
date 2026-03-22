# Refactor: Decompose bot.py into modules with aiogram Routers

## Context

`bot.py` is 750 lines containing all handler logic: helpers, keyboards, processing pipelines, commands, message handlers, callbacks, and entrypoint. As features grow (per-user settings plan already exists), this monolith will become harder to navigate and extend. The project already has a clean `services/` layer but no handler-level modularity and no use of aiogram Routers.

**Goal**: Split `bot.py` into focused modules using aiogram 3 Routers, so each file has a single responsibility and stays under ~200 lines. The `bot` instance stays in `bot.py`; handlers access it via aiogram's built-in dependency injection (`bot: Bot` kwarg).

## Target structure

```
bot.py                          ~50 lines   entrypoint: bot/dp creation, router assembly, main()
core/
  __init__.py                   empty
  helpers.py                    ~50 lines   _audio_suffix, _escape_md, _run_as_cancellable, _get_audio_from_msg
  keyboards.py                  ~55 lines   keyboard builders + UI label constants
  pipelines.py                  ~200 lines  process_youtube, process_audio, process_text
handlers/
  __init__.py                   empty
  commands.py                   ~170 lines  /start /mode /clear /model /savedoc /stop /ping /limits + mode/cancel callbacks
  messages.py                   ~120 lines  voice, audio, video_note, document, video, text, catch-all
  youtube_callbacks.py          ~55 lines   YT summary inline button callback
```

## Routers (3 total)

| Router | File | Handlers |
|--------|------|----------|
| `commands` | `handlers/commands.py` | All `/` commands + `mode:*` and `cancel` callback queries |
| `youtube_callbacks` | `handlers/youtube_callbacks.py` | `yt:*` callback queries |
| `messages` | `handlers/messages.py` | `F.voice`, `F.audio`, `F.video_note`, `F.document`, `F.video`, `F.text`, catch-all |

**Inclusion order in bot.py matters**: commands -> youtube_callbacks -> messages (catch-all must be last).

## Key design decisions

- **`bot` instance access**: Handlers receive `bot: Bot` as an injected kwarg from aiogram. Pipeline functions accept `bot` as an explicit parameter instead of using a global. This eliminates the global `bot` dependency everywhere except `bot.py`.
- **Pipelines separate from handlers**: `process_audio` (100 lines) and `process_youtube` (97 lines) are too large to inline in handler files. They live in `core/pipelines.py` and are called by handlers.
- **Drop `_` prefix on extracted functions**: Functions that become module-level public API lose the underscore (e.g., `_process_audio` -> `process_audio`, `_escape_md` -> `escape_md`).
- **Per-user settings fit**: Future `/settings` command becomes `handlers/settings.py` with its own Router — no existing files need restructuring.

## Extraction steps (ordered by dependency — extract leaves first)

### Step 1: `core/helpers.py` + `core/keyboards.py`

Extract pure utilities with zero coupling to handlers.

**`core/helpers.py`** — move from bot.py:
- `_audio_suffix()` (lines 51-68)
- `_escape_md()` (lines 71-75)
- `_run_as_cancellable()` (lines 78-87) — imports `active_tasks` from state
- `_get_audio_from_msg()` (lines 136-152) — uses `audio_suffix`

**`core/keyboards.py`** — move from bot.py:
- `_YT_LEVEL_MAP`, `_YT_LEVEL_LABELS` (lines 93-94)
- `_yt_summary_keyboard()` (lines 97-103)
- `_MODE_LABELS`, `_MODE_DESCRIPTIONS` (lines 109-118)
- `_mode_keyboard()` (lines 121-127)
- `_stop_keyboard()` (lines 130-133)

Update bot.py imports to use `from core.helpers import ...` and `from core.keyboards import ...`.

### Step 2: `core/pipelines.py`

Extract the three processing pipelines.

**Move from bot.py:**
- `_process_youtube()` (lines 158-255) -> `process_youtube(message, url, diarize)`
- `_process_audio()` (lines 260-358) -> `process_audio(message, bot, file_id, suffix)` — add `bot: Bot` parameter
- `_process_text()` (lines 589-610) -> `process_text(message)`

These import from: `core.helpers`, `core.keyboards`, `services.*`, `state`, `config`.

### Step 3: `handlers/commands.py`

Create `router = Router(name="commands")`. Move all command handlers:
- `cmd_start`, `cmd_mode`, `cmd_clear`, `cmd_model`, `cmd_savedoc`, `cmd_stop`, `cmd_ping`, `cmd_limits`
- `handle_mode_callback`, `handle_cancel_callback`

Change `@dp.message(Command(...))` to `@router.message(Command(...))`, same for callback queries.

### Step 4: `handlers/youtube_callbacks.py`

Create `router = Router(name="youtube_callbacks")`. Move:
- `handle_yt_summary_callback`

### Step 5: `handlers/messages.py`

Create `router = Router(name="messages")`. Move all message-type handlers:
- `handle_voice`, `handle_audio`, `handle_video_note`, `handle_document`, `handle_video`, `handle_text`, `handle_unhandled`

Each handler that calls `process_audio` passes `bot` from its injected kwarg:
```python
@router.message(F.voice)
async def handle_voice(message: types.Message, bot: Bot):
    if not is_allowed(message.from_user.id):
        return
    await run_as_cancellable(message.from_user.id, process_audio(message, bot, message.voice.file_id, ".ogg"))
```

### Step 6: Slim down `bot.py`

What remains (~50 lines):
- `bot = Bot(...)` and `dp = Dispatcher()`
- `dp.include_routers(commands_router, yt_callbacks_router, messages_router)`
- `async def main()` — register bot commands with Telegram, start polling
- `if __name__ == "__main__": asyncio.run(main())`

## Files to modify/create

| Action | File |
|--------|------|
| Create | `core/__init__.py` |
| Create | `core/helpers.py` |
| Create | `core/keyboards.py` |
| Create | `core/pipelines.py` |
| Create | `handlers/__init__.py` |
| Create | `handlers/commands.py` |
| Create | `handlers/messages.py` |
| Create | `handlers/youtube_callbacks.py` |
| Rewrite | `bot.py` (750 -> ~50 lines) |

No changes to: `config.py`, `state.py`, `services/*`.

## Verification

After each step, run the bot (`python bot.py`) and manually test:
1. **Step 1-2**: Send voice message, text, YouTube URL — all should work (imports changed, logic unchanged)
2. **Step 3**: Test `/start`, `/mode` (press inline buttons), `/clear`, `/model`, `/ping`, `/limits`, `/stop`, `/savedoc`
3. **Step 4**: Send YouTube URL, get transcript, press summary detail buttons (Brief/Detailed/Keypoints)
4. **Step 5-6**: Full regression — voice, audio file, video, text chat, YouTube URL, reply-to-audio, "stop" text command, catch-all for unsupported content
