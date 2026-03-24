# Structure & Dead Code Refactoring Plan

## Context

The project recently underwent a layered architecture migration (Phases 1-5) that moved code from a flat structure into `shared/`, `application/`, `domain/`, `infrastructure/`, `interfaces/` layers. Backward-compatibility shims were left at root level (`config.py`, `state.py`) so nothing would break. The migration is complete — all real logic lives in the new layers — but the shims remain, some files still import through them, and there's accumulated dead code.

## Current State Summary

### Architecture (post-migration)
```
bot.py                          # Entrypoint
config.py                       # SHIM: 150 lines of dead defs + `from shared.config import *`
state.py                        # SHIM: pure re-export of 55 symbols from application.state

shared/                         # Cross-cutting: config, i18n, keyboards, utils
application/                    # State management, rate limiting
domain/                         # Business logic: audio processing, YouTube, prompts
infrastructure/                 # DB, external APIs (LLM, Groq, Yandex), storage (Obsidian, GDocs)
interfaces/telegram/handlers/   # Telegram command/message handlers
tools/                          # Standalone CLI utilities (not part of bot runtime)
```

---

## Findings

### 1. Root `config.py` is 99% dead code
Lines 1-154 define constants, logging, etc. — then line 155 does `from shared.config import *` which **overwrites everything**. The entire body above line 155 is dead code that never takes effect. `shared/config.py` is the real config.

### 2. Root `state.py` is a pure re-export shim
105 lines that import 55 symbols from `application.state` and re-export them. No logic.

### 3. Inconsistent import paths (split callers)

**4 files still import from root `config` (shim):**
- `shared/i18n.py:9`
- `shared/keyboards.py:7`
- `domain/audio_processor.py:27`
- `domain/services/youtube.py:13`

**5 files still import from root `state` (shim):**
- `bot.py:16`
- `shared/i18n.py:122`
- `shared/utils.py:12`
- `interfaces/telegram/handlers/commands.py:111`
- `interfaces/telegram/handlers/settings.py:113, 350`

### 4. Dead functions

| Item | Location | Reason |
|------|----------|--------|
| `t_ru()` | `shared/i18n.py:144` | Never called anywhere |
| `t_en()` | `shared/i18n.py:149` | Never called anywhere |
| `MODE_DESCRIPTIONS` | `shared/keyboards.py:47` | Never referenced outside its definition |

### 5. Backward-compat constants with locale issues

| Item | Location | Issue |
|------|----------|-------|
| `MODE_LABELS` | `shared/keyboards.py:46` | Used by `commands.py:196` for validation — always default locale |
| `YT_LEVEL_LABELS` | `shared/keyboards.py:45` | Used by `youtube_callbacks.py:49` — always default locale |

These work but are semantically wrong for non-default-locale users (labels shown in default language). The fix is to call the private `_get_mode_labels(locale)` / `_get_yt_level_labels(locale)` functions directly.

### 6. Broken tool script
`tools/transcribe_cli.py:45` does `from bot import transcribe` — `bot.py` has no `transcribe` function. This script is non-functional.

---

## Refactoring Plan

### Phase 1: Delete root backward-compat shims (config.py, state.py)

**1a. Migrate `config` -> `shared.config` imports (4 files)**
- `shared/i18n.py:9`: `from config import ...` -> `from shared.config import ...`
- `shared/keyboards.py:7`: `from config import ...` -> `from shared.config import ...`
- `domain/audio_processor.py:27`: `from config import ...` -> `from shared.config import ...`
- `domain/services/youtube.py:13`: `from config import ...` -> `from shared.config import ...`

**1b. Migrate `state` -> `application.state` imports (5 files)**
- `bot.py:16`: `import state` -> `from application.state import initialize_state, shutdown_state`
- `shared/i18n.py:122`: `from state import get_language` -> `from application.state import get_language`
- `shared/utils.py:12`: `from state import active_tasks` -> `from application.state import active_tasks`
- `interfaces/telegram/handlers/commands.py:111`: `from state import ...` -> `from application.state import ...`
- `interfaces/telegram/handlers/settings.py:113,350`: `from state import ...` -> `from application.state import ...`

**1c. Delete shims**
- Delete `config.py` (root)
- Delete `state.py` (root)

### Phase 2: Remove dead code

- Delete `t_ru()` and `t_en()` from `shared/i18n.py` (lines 144-151)
- Delete `MODE_DESCRIPTIONS` from `shared/keyboards.py` (line 47)

### Phase 3: Fix backward-compat constants in keyboards.py

Replace module-level `MODE_LABELS` and `YT_LEVEL_LABELS` constants with direct function calls at use sites:

- `interfaces/telegram/handlers/commands.py:196`: replace `MODE_LABELS` usage with `get_mode_labels(locale)` (make function public: rename to `get_mode_labels`)
- `interfaces/telegram/handlers/youtube_callbacks.py:49`: replace `YT_LEVEL_LABELS` usage with `get_yt_level_labels(locale)`
- Delete the module-level constants (lines 44-47) from `shared/keyboards.py`
- Make `_get_mode_labels` and `_get_yt_level_labels` public (remove underscore prefix)

### Phase 4: Fix broken tool script

- `tools/transcribe_cli.py:45`: fix `from bot import transcribe` -> `from infrastructure.external_api.groq_client import transcribe`
- Remove `sys.path.insert` hack (line 44) if direct import works

### Phase 5: Update CLAUDE.md

Update the project structure section in CLAUDE.md to reflect the actual current directory layout (the current docs still describe the old flat structure with `core/`, `services/`, `handlers/` at root).

---

## Files Modified

| File | Action |
|------|--------|
| `config.py` (root) | DELETE |
| `state.py` (root) | DELETE |
| `shared/i18n.py` | Fix imports, delete `t_ru`/`t_en` |
| `shared/keyboards.py` | Fix imports, delete dead constants, make helpers public |
| `shared/utils.py` | Fix state import |
| `domain/audio_processor.py` | Fix config import |
| `domain/services/youtube.py` | Fix config import |
| `bot.py` | Fix state import |
| `interfaces/telegram/handlers/commands.py` | Fix state import, use `get_mode_labels()` |
| `interfaces/telegram/handlers/settings.py` | Fix state import |
| `interfaces/telegram/handlers/youtube_callbacks.py` | Use `get_yt_level_labels()` |
| `tools/transcribe_cli.py` | Fix broken import |
| `CLAUDE.md` | Update project structure docs |

## Verification

1. `python -c "import bot"` — verify bot loads without import errors
2. `ruff check .` — no lint errors
3. `pylint **/*.py` — no new warnings
4. Run the bot locally and test: send a voice message, use `/mode`, `/lang`, send a YouTube link
5. Verify tools still work: `python tools/audio_splitter.py --help`
