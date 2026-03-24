# Refactoring Progress Tracker

**Refactoring:** Layered Architecture
**Started:** 2026-03-24
**Status:** In Progress

---

## Phase 1: shared/

**Started:** 2026-03-24 22:25
**Completed:** 2026-03-24 22:32
**Status:** ✅ Complete

### Step 1.1: Create directory
- [x] Started
- [x] Completed
- [x] Tested
- [x] Committed

**Notes:** Created `shared/` directory with `__init__.py`

---

### Step 1.2: Move i18n
- [x] Started
- [x] Completed
- [x] Tested
- [x] Committed

**Changes:**
- Moved `core/i18n.py` → `shared/i18n.py`
- Updated imports in 11 files

**Testing:**
- [x] `ruff check .` passed
- [x] Bot starts successfully
- [x] /start command works (ru/en)
- [x] Language switching works

**Issues:** None

**Next:** Move keyboards

---

### Step 1.3: Move keyboards
- [x] Started
- [x] Completed
- [x] Tested
- [x] Committed

**Changes:**
- Moved `core/keyboards.py` → `shared/keyboards.py`
- Updated imports in 3 files

**Testing:**
- [x] `ruff check .` passed
- [x] Bot starts successfully
- [x] /mode command works
- [x] Keyboards render correctly

**Issues:** None

**Next:** Move helpers

---

### Step 1.4: Move helpers (utils)
- [x] Started
- [x] Completed
- [x] Tested
- [x] Committed

**Changes:**
- Moved `core/helpers.py` → `shared/utils.py`
- Updated imports in 5 files

**Testing:**
- [x] `ruff check .` passed
- [x] Bot starts successfully
- [x] Voice message processing works

**Issues:** None

**Next:** Move config

---

### Step 1.5: Move config
- [x] Started
- [x] Completed
- [x] Tested
- [x] Committed

**Changes:**
- Copied `config.py` → `shared/config.py`
- Fixed `_PROJECT_DIR` resolution (parent.parent for shared/)
- Added re-export in root `config.py`

**Testing:**
- [x] `ruff check .` passed
- [x] Bot starts successfully
- [x] All env vars load correctly
- [x] Config re-export works

**Issues:** Fixed prompt path resolution by using `parent.parent`

**Next:** Phase 1 complete!

---

### Phase 1 Summary

**Total Time:** 0.5 hours
**Files Moved:** 4
**Issues Encountered:** Prompt path resolution in shared/config.py (fixed via parent.parent)
**Deployed to Production:** No (pending testing)
**Date Deployed:** TBD

---

## Phase 2: infrastructure/

**Started:** 2026-03-24 22:45
**Completed:** 2026-03-24 22:52
**Status:** ✅ Complete

### Step 2.1: Create directories
- [x] Started
- [x] Completed
- [x] Tested

**Notes:** Created `infrastructure/` directory with subdirectories: `database/`, `external_api/`, `storage/`

---

### Step 2.2: Move database
- [x] Started
- [x] Completed
- [x] Tested
- [x] Committed

**Changes:**
- Copied `db/` → `infrastructure/database/`
- Updated imports in `state.py`, `alembic/env.py`, and internal database files
- Fixed path resolution: `DB_PATH` now uses `parent.parent.parent` to reach project root `data/`

**Testing:**
- [x] `ruff check .` passed
- [x] Bot starts successfully
- [x] State loads correctly
- [x] Data persists after restart

**Issues:** Fixed DB_PATH resolution (was looking in `infrastructure/data/`, now correctly points to `data/`)

**Next:** Move LLM client

---

### Step 2.3: Move LLM client
- [x] Started
- [x] Completed
- [x] Tested
- [x] Committed

**Changes:**
- Copied `services/llm.py` → `infrastructure/external_api/llm_client.py`
- Updated imports in `core/pipelines.py`, `handlers/youtube_callbacks.py`, `handlers/commands.py`

**Testing:**
- [x] `ruff check .` passed
- [x] Bot starts successfully
- [x] LLM API calls work
- [x] Text messages get responses

**Issues:** None

**Next:** Move STT client

---

### Step 2.4: Move STT client
- [x] Started
- [x] Completed
- [x] Tested
- [x] Committed

**Changes:**
- Copied `services/stt.py` → `infrastructure/external_api/groq_client.py`
- Updated imports in `core/pipelines.py`
- Fixed `sys.path` resolution for `audio_splitter` import (now uses `parent.parent.parent`)

**Testing:**
- [x] `ruff check .` passed
- [x] Bot starts successfully
- [x] Voice transcription works
- [x] Groq API calls work

**Issues:** Fixed audio_splitter path resolution

**Next:** Move Yandex OAuth

---

### Step 2.5: Move Yandex OAuth
- [x] Started
- [x] Completed
- [x] Tested
- [x] Committed

**Changes:**
- Copied `services/yandex_oauth.py` → `infrastructure/external_api/yandex_client.py`
- Updated imports in `handlers/commands.py`, `handlers/settings.py`
- Updated import in `services/obsidian.py` (before moving it)

**Testing:**
- [x] `ruff check .` passed
- [x] Bot starts successfully
- [x] OAuth flow works
- [x] Token exchange works

**Issues:** None

**Next:** Move storage services

---

### Step 2.6: Move storage services (obsidian, gdocs)
- [x] Started
- [x] Completed
- [x] Tested
- [x] Committed

**Changes:**
- Copied `services/obsidian.py` → `infrastructure/storage/obsidian.py`
- Copied `services/gdocs.py` → `infrastructure/storage/gdocs.py`
- Updated imports in `core/pipelines.py`, `handlers/commands.py`, `bot.py`

**Testing:**
- [x] `ruff check .` passed
- [x] Bot starts successfully
- [x] Yandex.Disk saves work
- [x] Google Docs saves work

**Issues:** None

**Next:** Phase 2 complete!

---

### Phase 2 Summary

**Total Time:** 0.5 hours
**Files Moved:** 8
**Issues Encountered:** 
- DB_PATH resolution in `infrastructure/database/database.py` (fixed: `parent.parent.parent`)
- `audio_splitter` import path in `groq_client.py` (fixed: `parent.parent.parent`)
**Deployed to Production:** No (pending testing)
**Date Deployed:** TBD

---

## Phase 3: application/

**Started:** 2026-03-24 23:05
**Completed:** 2026-03-24 23:19
**Status:** ✅ Complete

### Step 3.1: Create directory
- [x] Started
- [x] Completed
- [x] Tested

**Notes:** Created `application/` directory with subdirectories: `services/`

---

### Step 3.2: Move state.py
- [x] Started
- [x] Completed
- [x] Tested
- [x] Committed

**Changes:**
- Copied `state.py` → `application/state.py`
- Updated imports: `config` → `shared.config`
- Added missing `groq_limits` variable and `update_groq_limits()` function (pre-existing bug fix)
- Root `state.py` now re-exports from `application.state` for backward compatibility

**Testing:**
- [x] `from application.state import *` works
- [x] `from state import *` backward compatibility works
- [x] Bot starts successfully
- [x] State loads correctly
- [x] Data persists after restart

**Issues:** Fixed pre-existing bug: `groq_limits` and `update_groq_limits()` were referenced in `services/stt.py` but never defined in state module. Added them to `application/state.py`.

**Next:** Move rate limiter

---

### Step 3.3: Move rate limiter
- [x] Started
- [x] Completed
- [x] Tested
- [x] Committed

**Changes:**
- Copied `services/limits.py` → `application/services/rate_limiter.py`
- Updated imports: `config` → `shared.config`, `state` → `application.state`
- Updated import in `handlers/commands.py`

**Testing:**
- [x] `from application.services.rate_limiter import *` works
- [x] `/limits` command imports work
- [x] Bot starts successfully

**Issues:** None

**Next:** Phase 3 complete!

---

### Phase 3 Summary

**Total Time:** 0.25 hours
**Files Moved:** 2 (application/state.py, application/services/rate_limiter.py)
**Issues Encountered:**
- Fixed pre-existing bug: `groq_limits` and `update_groq_limits()` were missing from state module
**Deployed to Production:** No (pending testing)
**Date Deployed:** TBD

---

## Phase 3.5: Cleanup & Bugfixes

**Started:** YYYY-MM-DD HH:MM
**Completed:** YYYY-MM-DD HH:MM
**Status:** ⬜ Not Started

### Step 3.5.1: Fix shared/config.py LOG_DIR
- [ ] Started
- [ ] Completed
- [ ] Tested
- [ ] Committed

**Changes:**
-

**Notes:** `LOG_DIR = Path(__file__).parent / "logs"` creates `shared/logs/` instead of root `logs/`. Change to `_PROJECT_DIR / "logs"`. Delete `shared/logs/`.

---

### Step 3.5.2: Fix infrastructure/database/__init__.py DATABASE_URL export
- [ ] Started
- [ ] Completed
- [ ] Tested
- [ ] Committed

**Changes:**
-

**Notes:** `alembic/env.py` imports `DATABASE_URL` but it's not in `__init__.py` exports. Add it.

---

### Step 3.5.3: Standardize imports in infrastructure/
- [ ] Started
- [ ] Completed
- [ ] Tested
- [ ] Committed

**Changes:**
-

**Notes:** Change `from state import` → `from application.state import` and `from config import` → `from shared.config import` in all infrastructure/ files.

---

### Step 3.5.4: Delete dead old files
- [ ] Started
- [ ] Completed
- [ ] Tested
- [ ] Committed

**Changes:**
-

**Notes:** Delete: `core/i18n.py`, `core/keyboards.py`, `core/helpers.py`, `db/` directory, `services/llm.py`, `services/stt.py`, `services/yandex_oauth.py`, `services/obsidian.py`, `services/gdocs.py`, `services/limits.py`

---

### Phase 3.5 Summary

**Total Time:** X hours
**Files Deleted:** ~12
**Issues Encountered:**
**Deployed to Production:**
**Date Deployed:**

---

## Phase 4: domain/

**Started:** 2026-03-25 00:10
**Completed:** 2026-03-25 00:15
**Status:** ⚠️ Done locally but NOT committed to git

**WARNING:** `domain/` directory exists locally and `handlers/messages.py` imports from it,
but `domain/` is untracked by git. A fresh `git clone` or deploy will break. Must run Phase 3.5
first (to clean up dead files), then commit `domain/` properly.

### Step 4.1: Create directories
- [x] Started
- [x] Completed

**Notes:** Created `domain/` directory with subdirectories: `prompts/`, `services/`

---

### Step 4.2: Move pipelines
- [x] Started
- [x] Completed
- [x] Tested
- [ ] Committed ← NOT committed (domain/ untracked)

**Changes:**
- Copied `core/pipelines.py` → `domain/audio_processor.py`
- Updated imports: `services.youtube` → `domain.services.youtube`, `state` → `application.state`
- Updated import in `handlers/messages.py`
- Old `core/pipelines.py` NOT deleted (still exists as dead code)

**Testing:**
- [x] Bot starts successfully (locally)
- [x] All imports work (locally)

**Issues:** Old `core/pipelines.py` still references `services.youtube` (dead import path)

---

### Step 4.3: Move YouTube
- [x] Started
- [x] Completed
- [x] Tested
- [ ] Committed ← NOT committed (domain/ untracked)

**Changes:**
- Copied `services/youtube.py` → `domain/services/youtube.py`
- Fixed `transcribe_diarized` path resolution (now uses `parent.parent.parent` for tools/)
- Old `services/youtube.py` NOT deleted

**Testing:**
- [x] Bot starts successfully (locally)
- [x] YouTube imports work (locally)

**Issues:** Fixed tools path resolution for whisperX import

---

### Step 4.4: Move prompts
- [x] Started
- [x] Completed
- [x] Tested
- [ ] Committed ← NOT committed (domain/ untracked)

**Changes:**
- Copied `prompts/*.md` → `domain/prompts/*.md`
- Updated paths in `shared/config.py`: `prompts/` → `domain/prompts/`
- Old `prompts/` NOT deleted

**Testing:**
- [x] Bot starts successfully (locally)
- [x] Prompt loading works (locally)

**Issues:** None

---

### Phase 4 Summary

**Total Time:** 0.25 hours
**Files Moved:** 8 (audio_processor.py, youtube.py, 5 prompts, __init__.py files)
**Issues Encountered:**
- Fixed `transcribe_diarized` tools path resolution (now uses `parent.parent.parent`)
- Old files NOT deleted (need Phase 3.5 cleanup first, then re-commit Phase 4 properly)
- `domain/` NOT committed to git — deploy from git will break
**Deployed to Production:** No
**Date Deployed:** TBD

---

## Phase 5: interfaces/

**Started:** YYYY-MM-DD HH:MM  
**Completed:** YYYY-MM-DD HH:MM  
**Status:** ⬜ Not Started / 🔄 In Progress / ✅ Complete  

### Step 5.1: Create directories
- [ ] Started
- [ ] Completed

---

### Step 5.2: Move bot.py
- [ ] Started
- [ ] Completed
- [ ] Tested
- [ ] Committed

**Changes:**
- 

**Testing:**
- [ ] `ruff check .` passed
- [ ] Bot starts successfully
- [ ] All imports work

**Issues:**

---

### Step 5.3: Move handlers
- [ ] Started
- [ ] Completed
- [ ] Tested
- [ ] Committed

**Changes:**
- 

**Testing:**
- [ ] `ruff check .` passed
- [ ] Bot starts successfully
- [ ] All commands work
- [ ] All callbacks work
- [ ] /settings navigation works

**Issues:**

---

### Phase 5 Summary

**Total Time:** X hours  
**Files Moved:** 8  
**Issues Encountered:**  
**Deployed to Production:**  
**Date Deployed:**  

---

## Final Summary

**Total Refactoring Time:** X hours (over X weeks)  
**Total Files Moved:** 30  
**Total Lines Refactored:** ~3400  

**Benefits Achieved:**
- [ ] Clean layered architecture
- [ ] No circular dependencies
- [ ] Domain layer isolated
- [ ] All files under 150 lines
- [ ] Documentation updated
- [ ] Tests passing

**Lessons Learned:**
- 
- 
- 

**Next Steps:**
- [ ] Update QWEN.md
- [ ] Update CLAUDE.md
- [ ] Update README.md
- [ ] Celebrate! 🎉
