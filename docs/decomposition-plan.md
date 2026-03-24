# Code Decomposition Plan

Target: ~100 lines per file (range 50–150).

---

## 1. `application/state.py` (531 → 6 files)

**Root cause of bloat:** duplicated sync+async wrapper pairs with event-loop detection boilerplate.

| New file | Contents | Est. lines |
|----------|----------|-----------|
| `application/state.py` | Runtime in-memory state (`active_tasks`, `yt_transcripts`, `user_gdocs`, `user_modes`, `groq_limits`), `update_groq_limits()`, `cleanup_yt_cache()`, `can_use_shared_credentials()`, `get_mode/set_mode`, `get_language/set_language`, `initialize_state()`, `shutdown_state()` | ~90 |
| `application/user_settings.py` | `get_user_setting[_async]`, `set_user_setting[_async]`, `get_user_setting_json[_async]`, `set_user_setting_json[_async]`, `clear_user_setting[_async]`, `clear_user_settings_section[_async]` | ~120 |
| `application/conversation.py` | `add_to_history`, `_add_history_impl`, `get_history[_async]`, `clear_history[_async]` | ~80 |
| `application/free_uses.py` | `FREE_USES_LIMIT`, `get_free_uses[_async]`, `set_free_uses[_async]`, `increment_free_uses[_async]` | ~70 |
| `application/oauth_state.py` | `get_oauth_token_async`, `set_oauth_token_async`, `delete_oauth_token_async`, `get_or_create_user` | ~40 |
| `application/migration.py` | `migrate_legacy_data()`, `_JSON_FILE` constant | ~30 |

**Import sites to update:**
- `bot.py` — `initialize_state`, `shutdown_state`
- `shared/i18n.py` — `get_language`
- `shared/utils.py` — `active_tasks`
- `interfaces/telegram/handlers/commands.py` — `active_tasks`, `clear_history`, `get_history`, `get_language`, `get_mode`, `set_language`, `user_gdocs`, `user_modes`, `set_oauth_token_async`
- `interfaces/telegram/handlers/settings.py` — `clear_user_settings_section`, `get_user_setting`, `get_user_setting_json`, `set_user_setting`, `delete_oauth_token_async`
- `interfaces/telegram/handlers/youtube_callbacks.py` — `yt_transcripts`
- `interfaces/telegram/handlers/messages.py` — `active_tasks`
- `application/pipelines.py` — `FREE_USES_LIMIT`, `can_use_shared_credentials`, `cleanup_yt_cache`, `get_mode`, `get_user_setting`, `increment_free_uses`, `yt_transcripts`
- `application/services/rate_limiter.py` — `groq_limits`
- `infrastructure/external_api/llm_client.py` — `add_to_history`, `get_history`, `get_user_setting`
- `infrastructure/external_api/groq_client.py` — `update_groq_limits`
- `infrastructure/storage/gdocs.py` — `user_gdocs`
- `infrastructure/storage/obsidian.py` — `get_user_setting`, `get_user_setting_json`, `set_user_setting_json`

---

## 2. `infrastructure/database/database.py` (443 → 4 files)

| New file | Contents | Est. lines |
|----------|----------|-----------|
| `database/database.py` | `Database` class: `__init__`, `init_db`, `close`; `get_db()` factory | ~50 |
| `database/user_repo.py` | User CRUD + all UserSettings CRUD (`get_setting`, `set_setting`, `delete_setting`, etc.) | ~120 |
| `database/conversation_repo.py` | `add_conversation_message`, `get_conversation_history`, `clear_conversation` | ~40 |
| `database/oauth_repo.py` | `get_oauth_token`, `set_oauth_token`, `delete_oauth_token`, `get_free_uses`, `set_free_uses`, `increment_free_uses`, `migrate_from_json` | ~130 |

Repos receive `async_session_maker` via constructor or import from `database.py`.

---

## 3. `interfaces/telegram/handlers/settings.py` (443 → 3 files)

| New file | Contents | Est. lines |
|----------|----------|-----------|
| `handlers/settings_ui.py` | Keyboard builders (`_main_kb`, `_llm_kb`, `_yadisk_kb`, `_obsidian_kb`, `_cancel_kb`), text builders (`_llm_text`, `_yadisk_text`, `_obsidian_text`), helpers (`_mask`, `_val`), metadata dicts (`_KEY_META`, `_SUBMENU_FNS`, `_SUBMENU_KEYS`, `_SECRET_KEYS`, `_PRIVILEGED_KEYS`) | ~130 |
| `handlers/settings.py` | `SettingsStates`, `/settings` command, submenu/set/reset/cancel/value callbacks, `handle_setting_value` FSM | ~120 |
| `handlers/settings_oauth.py` | `cb_oauth_login`, `cb_oauth_disconnect` | ~60 |

---

## 4. `interfaces/telegram/handlers/commands.py` (365 → 3 files)

| New file | Contents | Est. lines |
|----------|----------|-----------|
| `handlers/commands.py` | `/start`, `/mode`, `/clear`, `/model`, `/savedoc`, `/stop`; mode/cancel callbacks | ~140 |
| `handlers/oauth_callback.py` | `cmd_start_oauth` deep-link handler | ~90 |
| `handlers/diagnostics.py` | `/ping`, `/limits`, `/lang`; lang callback | ~100 |

---

## 5. `application/pipelines.py` (309 → 3 files + package)

Convert `application/pipelines.py` → `application/pipelines/` package.

| New file | Contents | Est. lines |
|----------|----------|-----------|
| `pipelines/__init__.py` | Re-export `process_audio`, `process_youtube`, `process_text` | ~5 |
| `pipelines/audio.py` | `process_audio()`, `_check_free_tier()` | ~130 |
| `pipelines/youtube.py` | `process_youtube()` | ~90 |
| `pipelines/text.py` | `process_text()` | ~40 |

---

## 6. `infrastructure/external_api/llm_client.py` (194 → 2 files)

| New file | Contents | Est. lines |
|----------|----------|-----------|
| `external_api/llm_client.py` | `_default_client`, `_clients`, `_get_client()`, `_get_model()`, `_chat_with_retry()`, `ping_llm()` | ~70 |
| `external_api/llm_operations.py` | `ask_ollama()`, `summarize_ollama()`, `format_note_ollama()` | ~110 |

---

## 7. `infrastructure/external_api/yandex_client.py` (186) — leave as-is

Splitting would not bring it under 150 cleanly without creating a tiny `yandex_api.py` for just `get_user_login`. Not worth it.

---

## 8. `infrastructure/database/models.py` (171) — leave as-is

ORM models with relationships must stay together to avoid circular imports.

---

## Execution order

1. `state.py` — highest impact, unblocks cleaner callers
2. `database.py` — internal, no caller changes needed
3. `commands.py` — quick win, clear seams
4. `settings.py` — medium effort
5. `pipelines.py` — straightforward
6. `llm_client.py` — last, lowest risk
