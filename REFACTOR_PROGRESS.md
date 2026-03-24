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

**Started:** YYYY-MM-DD HH:MM  
**Completed:** YYYY-MM-DD HH:MM  
**Status:** ⬜ Not Started / 🔄 In Progress / ✅ Complete  

### Step 3.1: Create directory
- [ ] Started
- [ ] Completed

---

### Step 3.2: Move state.py
- [ ] Started
- [ ] Completed
- [ ] Tested
- [ ] Committed

**Changes:**
- 

**Testing:**
- [ ] `ruff check .` passed
- [ ] Bot starts successfully
- [ ] User settings load/save
- [ ] Conversation history works
- [ ] Data persists after restart

**Issues:**

---

### Step 3.3: Move rate limiter
- [ ] Started
- [ ] Completed
- [ ] Tested
- [ ] Committed

**Changes:**
- 

**Testing:**
- [ ] `ruff check .` passed
- [ ] Bot starts successfully
- [ ] /limits command works

**Issues:**

---

### Phase 3 Summary

**Total Time:** X hours  
**Files Moved:** 4  
**Issues Encountered:**  
**Deployed to Production:**  
**Date Deployed:**  

---

## Phase 4: domain/

**Started:** YYYY-MM-DD HH:MM  
**Completed:** YYYY-MM-DD HH:MM  
**Status:** ⬜ Not Started / 🔄 In Progress / ✅ Complete  

### Step 4.1: Create directories
- [ ] Started
- [ ] Completed

---

### Step 4.2: Move pipelines
- [ ] Started
- [ ] Completed
- [ ] Tested
- [ ] Committed

**Changes:**
- 

**Testing:**
- [ ] `ruff check .` passed
- [ ] Bot starts successfully
- [ ] Voice processing works
- [ ] All modes work

**Issues:**

---

### Step 4.3: Move YouTube
- [ ] Started
- [ ] Completed
- [ ] Tested
- [ ] Committed

**Changes:**
- 

**Testing:**
- [ ] `ruff check .` passed
- [ ] Bot starts successfully
- [ ] YouTube download works
- [ ] Summary generation works

**Issues:**

---

### Phase 4 Summary

**Total Time:** X hours  
**Files Moved:** 6  
**Issues Encountered:**  
**Deployed to Production:**  
**Date Deployed:**  

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
