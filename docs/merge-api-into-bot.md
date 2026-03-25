# Plan: merge API server into bot process

**Goal**: eliminate the separate `api` Docker container by running the FastAPI/uvicorn server
as a concurrent task inside the bot's existing asyncio event loop. Reduces peak RAM by ~200 MB.

## Why this works

Both `bot.py` and `interfaces/webapp/app.py` are asyncio-based. `uvicorn.Server.serve()` is a
coroutine that can run alongside `dp.start_polling()` under the same event loop via
`asyncio.gather()`. They already share the same DB singleton (`get_db()`), so no IPC or
file-sharing is needed.

## Changes

### 1. `shared/config.py`
Add in a new "Web API" section:
```python
WEBAPP_PORT = int(os.getenv("WEBAPP_PORT", "8080"))
WARP_PROXY = os.getenv("WARP_PROXY", "socks5://127.0.0.1:40000")
```

### 2. `interfaces/webapp/app.py`
Remove the `lifespan` entirely (or replace with a no-op). The DB is already initialised and
closed by `initialize_state()` / `shutdown_state()` in `bot.py`. Keeping a second lifespan
would double-init and double-close the same DB engine.

```python
# Before
@asynccontextmanager
async def lifespan(app: FastAPI):
    db = get_db()
    await db.init_db()
    ...
    yield
    await db.close()

app = FastAPI(..., lifespan=lifespan)

# After — drop lifespan argument
app = FastAPI(title="TG Bot Mini App API", version="1.0.0")
```

### 3. `bot.py`
Two changes:

**a) Scope the WARP proxy to specific HTTP clients** (not just aiogram). The bot communicates with
OpenRouter, Groq, and YouTube — all of which may require WARP. Configure proxy per-client:

```python
from aiogram.client.session.aiohttp import AiohttpSession
from shared.config import WARP_PROXY

# Aiogram session
session = AiohttpSession(proxy=WARP_PROXY) if WARP_PROXY else None
bot = Bot(token=BOT_TOKEN, session=session)

# In llm_client.py & groq_client.py:
client = httpx.AsyncClient(proxy=WARP_PROXY if WARP_PROXY else None)

# In youtube.py:
ydl_opts = {'proxy': WARP_PROXY if WARP_PROXY else None, ...}
```

**b) Run uvicorn as a concurrent asyncio task** with proper signal handling and graceful shutdown:

```python
import uvicorn
from interfaces.webapp.app import app as webapp
from shared.config import WEBAPP_PORT

async def main():
    ...
    await initialize_state()
    ...

    config = uvicorn.Config(
        webapp, 
        host="0.0.0.0", 
        port=WEBAPP_PORT,
        log_config=None,               # Inherit bot's rotating file logging
        install_signal_handlers=False  # Prevent signal clashes with aiogram
    )
    server = uvicorn.Server(config)

    try:
        await asyncio.gather(
            dp.start_polling(bot),
            server.serve(),
        )
    except asyncio.CancelledError:
        pass  # Expected on shutdown
    finally:
        # 1. Signal uvicorn to stop accepting requests
        server.should_exit = True
        
        # 2. Allow in-flight requests to finish (prevents DB connection errors)
        await asyncio.sleep(0.5)
        
        # 3. Clean up bot and DB state last
        await shutdown_state()
        await bot.session.close()
```

Note: `install_signal_handlers=False` prevents uvicorn from double-trapping SIGINT/SIGTERM,
which causes warnings and hangs. The graceful sleep buffer prevents pending API requests from
hitting a closed database connection.

### 4. `docker/docker-entrypoint.sh`
Remove the two lines that set the global proxy env vars — they are no longer needed since the
proxy is now configured per-client in `bot.py` and `llm_client.py`/`groq_client.py`/`youtube.py`:

```sh
# Remove these:
export HTTP_PROXY="socks5://127.0.0.1:40000"
export HTTPS_PROXY="socks5://127.0.0.1:40000"
```

**Important:** The WARP proxy must be configured in each HTTP client (`httpx.AsyncClient`, 
`yt-dlp`) to ensure all external API calls (OpenRouter, Groq, YouTube) route through WARP.

### 5. `docker/docker-compose.yml`
- Remove the `api` service block entirely.
- Add `ports: ["8080:8080"]` to the `bot` service.
- Remove `api` from caddy's `depends_on` (keep `frontend`).

```yaml
  bot:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    restart: unless-stopped
    ports:
      - "8080:8080"
    volumes:
      - ../data:/app/data
      - ../logs:/app/logs
    env_file:
      - ../.env
    cap_add:
      - NET_ADMIN

  caddy:
    ...
    depends_on:
      - bot
      - frontend
```

### 6. `Caddyfile`
Change the upstream from `api:8080` to `bot:8080`:
```
handle /api/* {
    reverse_proxy bot:8080
}
```

### 7. `docker/Dockerfile.api` — delete
No longer needed. `fastapi`, `uvicorn[standard]`, and `python-multipart` are already in
`requirements.txt` and thus present in the main `Dockerfile`.

## Shutdown behaviour

| Scenario | What happens |
|---|---|
| Bot exits normally (Ctrl-C / SIGTERM) | `dp.start_polling` returns → `gather` cancels `server.serve()` → `finally` sets `server.should_exit = True`, waits 0.5s for in-flight requests, then cleans up |
| Uvicorn crashes | `gather` propagates exception → bot polling is cancelled → `finally` waits 0.5s, then cleans up |
| SIGTERM to container | Docker sends SIGTERM → Python raises `KeyboardInterrupt` → same path as Ctrl-C |

**Key improvements:**
- `install_signal_handlers=False` prevents uvicorn from double-trapping signals
- `await asyncio.sleep(0.5)` allows pending API requests to complete before DB closes
- `log_config=None` ensures uvicorn uses the bot's existing rotating file logging

## Files touched

| File | Action |
|---|---|
| `shared/config.py` | add `WEBAPP_PORT`, `WARP_PROXY` |
| `interfaces/webapp/app.py` | remove lifespan |
| `bot.py` | scope WARP to HTTP clients; add uvicorn task with graceful shutdown |
| `infrastructure/external_api/llm_client.py` | add proxy to httpx client |
| `infrastructure/external_api/groq_client.py` | add proxy to httpx client |
| `infrastructure/external_api/youtube.py` | add proxy to yt-dlp options |
| `docker/docker-entrypoint.sh` | remove global `HTTP_PROXY`/`HTTPS_PROXY` exports |
| `docker/docker-compose.yml` | remove `api` service, add port to `bot`, fix caddy depends_on |
| `Caddyfile` | change upstream to `bot:8080` |
| `docker/Dockerfile.api` | delete |
