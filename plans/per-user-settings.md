# Plan: Per-user settings via Telegram bot

## Goal

Let each Telegram user override Yandex Disk, Obsidian vault, and LLM API
credentials directly in the bot via `/settings` command, without touching `.env`.

## Files to change

### 1. `state.py` — add `user_settings` store with persistence

```python
user_settings: dict[int, dict] = {}

def get_user_setting(user_id: int, key: str, default=None)
def set_user_setting(user_id: int, key: str, value: str) -> None
def clear_user_setting(user_id: int, key: str) -> None
def save_user_settings() -> None      # persist to disk
def load_user_settings() -> None      # load on startup
```

Fallback chain: `user_settings[user_id][key]` → `config.CONSTANT`

**Persistence**: Store settings in a JSON file (e.g. `data/user_settings.json`).
Credentials (API keys, passwords) are re-entered on every restart otherwise.
Encrypt or at least restrict file permissions (0600). Call `save_user_settings()`
after every `set_user_setting` / `clear_user_setting`; call `load_user_settings()`
at bot startup.

---

### 2. `services/obsidian.py` — accept `user_id`

Change signatures:
- `is_obsidian_enabled(user_id: int) -> bool`
- `save_note(filename: str, content: str, user_id: int) -> str`

Resolve config per-user (falling back to global constants if not set):
- `yadisk_login`, `yadisk_password`, `yadisk_path`
- `obsidian_vault_path`, `obsidian_inbox_folder`

---

### 3. `services/llm.py` — dynamic client per user

Replace module-level `_client` with a cached factory:

```python
_clients: dict[tuple[str, str], openai.AsyncOpenAI] = {}

def _get_client(api_key: str, base_url: str) -> openai.AsyncOpenAI:
    """Return a cached AsyncOpenAI client for the given credentials."""
    key = (api_key, base_url)
    if key not in _clients:
        _clients[key] = openai.AsyncOpenAI(api_key=api_key, base_url=base_url, ...)
    return _clients[key]
```

Keep the default global client as before (for users without overrides).

Update these functions to accept `user_id: int` and resolve effective
`api_key` / `base_url` / `model` from user settings, falling back to globals:
- `ask_ollama`
- `summarize_ollama`
- `format_note_ollama`
- `ping_llm` (currently also uses global `_client` and `LLM_MODEL`)
- `_chat_with_retry` — accept a `client` parameter instead of using module-level `_client`

---

### 4. `handlers/settings.py` (new) — `/settings` command + FSM

- Create a new router for settings handlers
- Add `SettingsState` FSM group with state `waiting_for_value`
  (stores which key is being set in FSM data)
- Add `/settings` command handler and inline keyboard callbacks
- **Delete the user's message** immediately after reading a secret value
  (`await message.delete()`) to prevent API keys / passwords lingering in chat history
- Bot replies should mask secrets (e.g. `API Key: sk-...xxxx (set)`, never echo full value)

### 5. `bot.py` — register settings router + FSM storage

- Add `MemoryStorage` to `Dispatcher`
- Include `settings_router` **before** `messages_router` (catch-all) so FSM
  state handlers fire first
- Call `state.load_user_settings()` at startup

### 6. `handlers/messages.py` — add state filter to catch-all

- Add `StateFilter(None)` (or `default_state`) to the catch-all text/voice
  handlers so they don't intercept messages when the user is in FSM
  `waiting_for_value` state

### 7. `handlers/commands.py`, `handlers/messages.py`, `handlers/youtube_callbacks.py` — pass `user_id`

- Update all calls to `is_obsidian_enabled()`, `save_note()`, `ask_ollama()`,
  `summarize_ollama()`, `format_note_ollama()` to pass `user_id`
- These are the actual call sites (not `bot.py` which only wires routers)

---

## UX flow

```
/settings
  ┌──────────────────────────────────────────┐
  │  [LLM API]   [Yandex.Disk]   [Obsidian]  │
  └──────────────────────────────────────────┘

  LLM API submenu:
    API Key:  ••• (set) / not set
    Base URL: https://openrouter.ai/api/v1
    Model:    qwen/qwen3-235b-a22b:free
    [Set API Key]  [Set Base URL]  [Set Model]  [Reset]  [Back]

  Yandex.Disk submenu:
    Login:    user@ya.ru / not set
    Password: ••• (set) / not set
    Path:     ObsidianVault
    [Set Login]  [Set Password]  [Set Path]  [Clear all]  [Back]

  Obsidian (local) submenu:
    Vault Path:    /path/to/vault / not set
    Inbox Folder:  Inbox
    [Set Vault Path]  [Set Inbox Folder]  [Clear]  [Back]
```

Clicking "Set X":
1. Bot replies: "Send the value:"
2. FSM enters `waiting_for_value` (stores target key in data)
3. User sends value → saved to `user_settings` → bot returns to submenu

Clicking "Reset" / "Clear": removes user's override, falls back to global default.

---

## Security considerations

1. **Delete secret messages**: After the user sends an API key or password,
   immediately `await message.delete()` so it doesn't stay in chat history.
   Never echo the full value back — mask it (e.g. `sk-...xxxx`).

2. **Obsidian local path — directory traversal risk**: If the bot runs on a
   shared server, letting any allowed user set `OBSIDIAN_VAULT_PATH` enables
   arbitrary file writes. Mitigations:
   - Only allow the bot owner (first ALLOWED_USER) to set local paths, OR
   - Validate that the path is under a configured allowed root, OR
   - Skip local-path override entirely (only allow Yandex.Disk per-user)

3. **Settings file permissions**: The persisted `data/user_settings.json` contains
   secrets. Set file permissions to 0600 on creation.

4. **Input validation**: Validate user-provided values before storing:
   - `base_url`: must be a valid URL (basic URL parse check)
   - `api_key`: non-empty, reasonable length limit
   - `model`: non-empty string, no special characters
   - Optional: "test connection" button to verify LLM credentials work

---

## Registration UX options (per setting type)

### Option A: Telegram Mini App (Web App)

A button opens an in-app browser with a hosted HTTPS page. The page handles OAuth
redirects and forms, then calls `window.Telegram.WebApp.sendData(json)` to pass
credentials back to the bot.

- **Pros**: Full OAuth support, real forms, good UX
- **Cons**: Requires a hosted HTTPS page

Best for: Yandex OAuth (get a token instead of storing login/password)

### Option B: URL button → external OAuth → webhook callback

1. Bot sends a button with the OAuth authorization URL
2. User authorizes in browser
3. Service redirects to your callback URL
4. Callback stores the token and notifies the bot

- **Pros**: Standard OAuth2 flow, no credentials stored
- **Cons**: Requires a public URL (webhook server), more infrastructure

### Option C: Text FSM (current plan)

User pastes credentials/keys as text messages in the chat.

- **Pros**: Zero extra infrastructure, works now
- **Cons**: Not suitable for OAuth; passwords in chat history

---

## Recommended approach per setting

| Setting         | Recommended UX                            |
|-----------------|-------------------------------------------|
| LLM API Key     | Text FSM — user pastes key in chat        |
| Yandex Disk     | Mini App or URL button → Yandex OAuth2    |
| Obsidian path   | Text FSM — just a local path string       |

The FSM plan above covers LLM API Key and Obsidian path well as-is.
Yandex Disk ideally uses OAuth to avoid storing login/password.

---

## Free tier: usage limits for shared credentials

Users who haven't configured their own credentials get a limited number of free
uses of the bot's global (shared) API keys. After the limit is reached, the bot
stops processing and asks the user to set up their own credentials via `/settings`.

### Rules

- **What counts as a use**: every LLM call AND every STT call (transcription).
  Each pipeline invocation (`process_audio`, `process_text`, `process_youtube`)
  that hits LLM or STT increments the counter.
- **Limit**: `FREE_USES_LIMIT = 3` (configurable constant).
- **Who is affected**: all users EXCEPT those listed in `ALLOWED_USERS` env var.
  Allowed users have unlimited access to shared credentials.
- **Persistence**: counters are saved to `data/user_settings.json` alongside
  user settings, so they survive bot restarts.

### Implementation outline

#### `state.py`

```python
FREE_USES_LIMIT = 3

# Persisted in data/user_settings.json alongside user_settings
user_free_uses: dict[int, int] = {}

def get_free_uses(user_id: int) -> int:
    return user_free_uses.get(user_id, 0)

def increment_free_uses(user_id: int) -> int:
    """Increment and return the new count. Persists to disk."""
    user_free_uses[user_id] = user_free_uses.get(user_id, 0) + 1
    save_user_settings()
    return user_free_uses[user_id]

def has_free_uses_left(user_id: int) -> bool:
    return get_free_uses(user_id) < FREE_USES_LIMIT
```

#### Check logic (in pipelines or a decorator)

```python
def can_use_shared_credentials(user_id: int) -> bool:
    """Return True if the user may use the bot's global API keys."""
    # Allowed users always can
    if user_id in config.ALLOWED_USER_IDS:
        return True
    # User has own credentials — no limit
    if get_user_setting(user_id, "llm_api_key"):
        return True
    # Free tier check
    return has_free_uses_left(user_id)
```

Before calling LLM/STT:
1. Call `can_use_shared_credentials(user_id)`.
2. If **yes**: increment counter, proceed. Optionally warn:
   - "You have N of 3 free uses remaining. Set your own API key via /settings."
3. If **no**: block with message:
   - "You've used all 3 free requests. Please set up your own API key via
     /settings to continue using the bot."

### UX

- After each free use, show remaining count (e.g. "2/3 free uses remaining").
- On the 3rd use, include a note: "This is your last free use."
- After limit reached, every message gets a block response pointing to `/settings`.
- Once the user sets their own API key, the limit no longer applies.
