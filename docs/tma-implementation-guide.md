# TMA & Bot Upgrades v2.0 — Technical Implementation Guide

## Phase 1: Infrastructure (Redis + DB Migration)

### 1.1 New Dependencies

```
# pyproject.toml additions
redis[hiredis] >= 5.0
sse-starlette >= 2.0
```

### 1.2 Database Schema: `BotMessage` Model

Add to `infrastructure/database/models.py`:

```python
from sqlalchemy import BigInteger

class BotMessage(Base):
    """Tracks bot/user message IDs for 48h deletion window."""
    __tablename__ = "bot_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger)
    direction: Mapped[str] = mapped_column(String(4))  # "in" or "out"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        Index("idx_bot_messages_user_created", "user_id", "created_at"),
    )
```

Add a `bot_messages` relationship to the `User` model and a new `BotMessageRepo`:

```python
# infrastructure/database/bot_message_repo.py
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, delete
from infrastructure.database.models import BotMessage

class BotMessageRepo:
    def __init__(self, session_maker):
        self._session_maker = session_maker

    async def track(self, user_id: int, chat_id: int, message_id: int, direction: str):
        async with self._session_maker() as session:
            session.add(BotMessage(
                user_id=user_id, chat_id=chat_id,
                message_id=message_id, direction=direction,
            ))
            await session.commit()

    async def get_deletable(self, user_id: int, chat_id: int) -> list[BotMessage]:
        """Get bot-sent messages within 48h window."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        async with self._session_maker() as session:
            result = await session.execute(
                select(BotMessage)
                .where(
                    BotMessage.user_id == user_id,
                    BotMessage.chat_id == chat_id,
                    BotMessage.direction == "out",
                    BotMessage.created_at >= cutoff,
                )
                .order_by(BotMessage.created_at.desc())
            )
            return list(result.scalars().all())

    async def purge_expired(self):
        """Delete records older than 48h — call from background task."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        async with self._session_maker() as session:
            await session.execute(
                delete(BotMessage).where(BotMessage.created_at < cutoff)
            )
            await session.commit()
```

### 1.3 Redis Connection Singleton

```python
# infrastructure/redis_client.py
import logging
from typing import Optional
import redis.asyncio as redis
from shared.config import REDIS_URL  # add REDIS_URL to config.py

logger = logging.getLogger(__name__)

_pool: Optional[redis.Redis] = None

async def get_redis() -> redis.Redis:
    global _pool
    if _pool is None:
        _pool = redis.from_url(REDIS_URL, decode_responses=True)
        logger.info("Redis connected: %s", REDIS_URL)
    return _pool

async def close_redis():
    global _pool
    if _pool:
        await _pool.aclose()
        _pool = None
```

Wire `close_redis()` into `shutdown_state()` in `application/state.py`, and add `REDIS_URL` (default `redis://localhost:6379/0`) to `shared/config.py`.

### 1.4 Migration Script

Create `infrastructure/database/migrations/003_add_bot_messages.py` using the existing migration pattern. Since `Base.metadata.create_all` is used in `init_db()`, the table will be auto-created — but for production safety, also add:

```python
# infrastructure/database/migrations/003_add_bot_messages.py
async def upgrade(engine):
    async with engine.begin() as conn:
        await conn.run_sync(BotMessage.__table__.create, checkfirst=True)
```

---

## Phase 2: Message Deletion (`/clear` Upgrade)

### 2.1 Tracking Middleware

Register an aiogram outer middleware that logs every incoming and outgoing message ID:

```python
# interfaces/telegram/middleware/message_tracker.py
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from typing import Any, Callable, Awaitable
from infrastructure.database.database import get_db

class MessageTrackingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Track incoming user message
        if isinstance(event, Message) and event.from_user and event.chat:
            db = get_db()
            await db.track_message(
                user_id=event.from_user.id,
                chat_id=event.chat.id,
                message_id=event.message_id,
                direction="in",
            )

        result = await handler(event, data)

        # Track outgoing bot responses
        if isinstance(result, Message) and result.chat:
            db = get_db()
            await db.track_message(
                user_id=event.from_user.id if isinstance(event, Message) and event.from_user else 0,
                chat_id=result.chat.id,
                message_id=result.message_id,
                direction="out",
            )

        return result
```

Register in `bot.py`:

```python
from interfaces.telegram.middleware.message_tracker import MessageTrackingMiddleware
dp.message.outer_middleware(MessageTrackingMiddleware())
```

### 2.2 Enhanced `/clear` with Batch Deletion

Replace the current `/clear` handler in `interfaces/telegram/handlers/commands.py`:

```python
import asyncio
from infrastructure.database.database import get_db

@router.message(Command("clear"))
async def cmd_clear(message: types.Message):
    locale = await get_locale_from_message(message)
    from_user = message.from_user
    if not from_user or not is_allowed(from_user.id):
        return

    # 1. Clear conversation history (existing logic)
    clear_history(from_user.id)

    # 2. Delete tracked messages from Telegram (batch of 25, 1s sleep)
    db = get_db()
    messages_to_delete = await db.get_deletable_messages(from_user.id, message.chat.id)

    deleted = 0
    failed = 0
    for i in range(0, len(messages_to_delete), 25):
        batch = messages_to_delete[i:i + 25]
        for msg in batch:
            try:
                await message.bot.delete_message(chat_id=msg.chat_id, message_id=msg.message_id)
                deleted += 1
            except Exception:
                failed += 1  # Message already deleted or >48h
        if i + 25 < len(messages_to_delete):
            await asyncio.sleep(1)  # Rate limit: 25 deletions per second

    logger.info("/clear user_id=%d deleted=%d failed=%d", from_user.id, deleted, failed)
    await message.answer(t("commands.clear.history_cleared", locale))
```

### 2.3 Background Cleanup Task

Add to `bot.py`'s `main()` function alongside polling:

```python
async def purge_expired_messages():
    """Background task: clean up bot_messages older than 48h every hour."""
    db = get_db()
    while True:
        await asyncio.sleep(3600)
        try:
            await db.purge_expired_messages()
        except Exception as e:
            logger.warning("purge_expired_messages failed: %s", e)

# In asyncio.gather:
await asyncio.gather(
    dp.start_polling(bot),
    server.serve(),
    purge_expired_messages(),
)
```

---

## Phase 3: Redis-backed SSE for OAuth Sync

### 3.1 SSE Endpoint

```python
# interfaces/webapp/routes/oauth.py — add SSE endpoint
import asyncio
import json
from sse_starlette.sse import EventSourceResponse
from infrastructure.redis_client import get_redis

@router.get("/oauth/events")
async def oauth_events(request: Request, auth: str = Query(...)):
    """SSE stream for real-time OAuth state updates."""
    user = validate_init_data(auth, BOT_TOKEN)
    user_id = user["id"]

    async def event_generator():
        r = await get_redis()
        pubsub = r.pubsub()
        channel = f"oauth_updates:{user_id}"
        await pubsub.subscribe(channel)

        try:
            # Initial state push
            db = get_db()
            token = await db.get_oauth_token(user_id, "yandex")
            yield {
                "event": "oauth_state",
                "data": json.dumps({
                    "provider": "yandex",
                    "connected": token is not None,
                    "login": json.loads(token.token_meta or "{}").get("login") if token else None,
                }),
            }

            # Listen for updates
            while True:
                if await request.is_disconnected():
                    break
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message and message["type"] == "message":
                    yield {"event": "oauth_state", "data": message["data"]}
                await asyncio.sleep(0.1)
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    return EventSourceResponse(event_generator())
```

### 3.2 Publish on OAuth Callback

In the existing OAuth callback handler, after successfully storing the token:

```python
# After set_oauth_token succeeds:
from infrastructure.redis_client import get_redis

r = await get_redis()
await r.publish(
    f"oauth_updates:{user_id}",
    json.dumps({
        "provider": "yandex",
        "connected": True,
        "login": yandex_login,
    }),
)
```

Similarly, on disconnect:

```python
await r.publish(
    f"oauth_updates:{user_id}",
    json.dumps({"provider": "yandex", "connected": False, "login": None}),
)
```

### 3.3 Frontend SSE Consumer (TypeScript/React)

```typescript
// src/hooks/useOAuthSSE.ts
import { useEffect, useState, useCallback } from "react";

interface OAuthState {
  provider: string;
  connected: boolean;
  login: string | null;
}

export function useOAuthSSE(initData: string) {
  const [state, setState] = useState<OAuthState | null>(null);

  const fetchState = useCallback(async () => {
    // Fallback: manual fetch when SSE drops
    const res = await fetch(`/api/v1/oauth/yandex/status?auth=${encodeURIComponent(initData)}`);
    if (res.ok) setState(await res.json());
  }, [initData]);

  useEffect(() => {
    const url = `/api/v1/oauth/events?auth=${encodeURIComponent(initData)}`;
    const es = new EventSource(url);

    es.addEventListener("oauth_state", (e) => {
      setState(JSON.parse(e.data));
    });

    es.onerror = () => {
      es.close();
      // Reconnect after 3s
      setTimeout(() => fetchState(), 3000);
    };

    // Fallback: refetch on tab visibility change
    const onVisibility = () => {
      if (document.visibilityState === "visible") fetchState();
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      es.close();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [initData, fetchState]);

  return state;
}
```

---

## Phase 4: TMA Frontend (Notes / Usage / Settings Tabs)

### 4.1 React App Structure

```
tma/
├── public/
│   └── index.html
├── src/
│   ├── App.tsx                  — Root: tabs + deep-link router
│   ├── main.tsx                 — Entry: Telegram.WebApp.ready()
│   ├── api/client.ts            — Fetch wrapper with initData auth
│   ├── hooks/
│   │   ├── useOAuthSSE.ts       — Real-time OAuth (above)
│   │   ├── useTelegram.ts       — window.Telegram.WebApp helpers
│   │   └── useDeepLink.ts       — Parse startapp param
│   ├── components/
│   │   ├── TabBar.tsx           — Bottom navigation
│   │   ├── NoteCard.tsx         — Single note preview
│   │   └── UsageBar.tsx         — Rate limit progress bar
│   └── pages/
│       ├── NotesTab.tsx         — Conversation history + notes viewer
│       ├── UsageTab.tsx         — Rate limits, free uses, model info
│       └── SettingsTab.tsx      — Mode, language, Yandex OAuth toggle
```

### 4.2 Entry Point & Telegram SDK Init

```typescript
// src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();         // Full-height mode
tg.enableClosingConfirmation();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App initData={tg.initData} startParam={tg.initDataUnsafe?.start_param ?? null} />
  </React.StrictMode>
);
```

### 4.3 Deep Linking via `startapp`

```typescript
// src/hooks/useDeepLink.ts
interface DeepLink {
  page: "notes" | "usage" | "settings" | "note_detail";
  noteId?: string;
}

export function parseDeepLink(startParam: string | null): DeepLink | null {
  if (!startParam) return null;

  // e.g. startapp=note_123 → open note detail
  if (startParam.startsWith("note_")) {
    return { page: "note_detail", noteId: startParam.slice(5) };
  }
  // e.g. startapp=settings
  if (["notes", "usage", "settings"].includes(startParam)) {
    return { page: startParam as DeepLink["page"] };
  }
  return null;
}
```

### 4.4 App.tsx with Tab Router

```typescript
// src/App.tsx
import { useState, useEffect } from "react";
import { parseDeepLink } from "./hooks/useDeepLink";
import { useOAuthSSE } from "./hooks/useOAuthSSE";
import NotesTab from "./pages/NotesTab";
import UsageTab from "./pages/UsageTab";
import SettingsTab from "./pages/SettingsTab";
import TabBar from "./components/TabBar";

type Tab = "notes" | "usage" | "settings";

export default function App({ initData, startParam }: { initData: string; startParam: string | null }) {
  const deepLink = parseDeepLink(startParam);
  const [tab, setTab] = useState<Tab>(deepLink?.page === "note_detail" ? "notes" : (deepLink?.page ?? "notes"));
  const oauthState = useOAuthSSE(initData);

  // Telegram MainButton: context-sensitive action
  const tg = window.Telegram.WebApp;
  useEffect(() => {
    if (tab === "settings") {
      tg.MainButton.setText("Save Settings");
      tg.MainButton.show();
      tg.MainButton.onClick(() => {
        tg.HapticFeedback.impactOccurred("light");
        // trigger settings save
      });
    } else {
      tg.MainButton.hide();
    }
    return () => tg.MainButton.offClick(() => {});
  }, [tab]);

  return (
    <div style={{ paddingBottom: 60 }}>
      {tab === "notes" && <NotesTab initData={initData} noteId={deepLink?.noteId} />}
      {tab === "usage" && <UsageTab initData={initData} />}
      {tab === "settings" && <SettingsTab initData={initData} oauthState={oauthState} />}
      <TabBar active={tab} onChange={setTab} />
    </div>
  );
}
```

### 4.5 Telegram Native Features

```typescript
// src/hooks/useTelegram.ts
export function useTelegram() {
  const tg = window.Telegram.WebApp;

  return {
    haptic: (type: "light" | "medium" | "heavy") => tg.HapticFeedback.impactOccurred(type),
    confirm: (msg: string) =>
      new Promise<boolean>((resolve) => tg.showConfirm(msg, resolve)),
    close: () => tg.close(),
    themeParams: tg.themeParams,
    colorScheme: tg.colorScheme,
  };
}
```

### 4.6 Settings Tab with OAuth

```typescript
// src/pages/SettingsTab.tsx
import { useTelegram } from "../hooks/useTelegram";

export default function SettingsTab({ initData, oauthState }) {
  const { haptic } = useTelegram();

  const handleYandexConnect = () => {
    haptic("medium");
    // Open OAuth URL in Telegram's external browser
    window.Telegram.WebApp.openLink(
      `/api/v1/oauth/yandex/authorize?auth=${encodeURIComponent(initData)}`
    );
  };

  return (
    <div>
      <h2>Yandex.Disk</h2>
      {oauthState?.connected ? (
        <div>
          Connected as <strong>{oauthState.login}</strong>
          <button onClick={handleDisconnect}>Disconnect</button>
        </div>
      ) : (
        <button onClick={handleYandexConnect}>Connect Yandex.Disk</button>
      )}
      {/* Mode selector, language picker, etc. */}
    </div>
  );
}
```

---

## Phase 5: Deep Linking & Entry Points

### 5.1 Menu Button (Backend)

Add to `bot.py` after setting commands:

```python
from aiogram.types import MenuButtonWebApp, WebAppInfo
from shared.config import WEBAPP_URL  # e.g. "https://your-domain.com/tma"

try:
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="Open App",
            web_app=WebAppInfo(url=WEBAPP_URL),
        )
    )
except Exception as e:
    logger.warning("Failed to set menu button: %s", e)
```

### 5.2 Inline "Edit & Save" Button After Processing

In the audio/text/youtube pipelines, after sending a result, attach an inline button:

```python
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

def edit_in_tma_button(note_id: str, locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=t("tma.edit_and_save", locale),
            web_app=WebAppInfo(url=f"{WEBAPP_URL}?startapp=note_{note_id}"),
        )
    ]])
```

### 5.3 `/settings` Opens TMA

Replace the current `/settings` FSM handler with a TMA redirect:

```python
@router.message(Command("settings"))
async def cmd_settings(message: types.Message):
    locale = await get_locale_from_message(message)
    from_user = message.from_user
    if not from_user or not is_allowed(from_user.id):
        return

    await message.answer(
        t("commands.settings.open_tma", locale),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text=t("commands.settings.button", locale),
                web_app=WebAppInfo(url=f"{WEBAPP_URL}?startapp=settings"),
            )
        ]]),
    )
```

---

## Security Checklist

| Concern | Implementation |
|---|---|
| **initData validation** | HMAC-SHA256 on every request (existing `interfaces/webapp/auth.py`) |
| **SSE auth** | `auth` query param validated before subscribing to Redis channel |
| **OAuth state binding** | Server-generated `state` token ties Yandex redirect to `user_id` (existing OAuth flow) |
| **Redis channel isolation** | Channels namespaced by `user_id` — no cross-user leakage |
| **CORS** | Tighten `allow_origins` to TMA domain in production |

---

## New Environment Variables

```env
REDIS_URL=redis://localhost:6379/0
WEBAPP_URL=https://your-domain.com/tma    # Public URL for TMA deep links
```

## Dependency Summary

| Package | Purpose | Phase |
|---|---|---|
| `redis[hiredis]` | Pub/Sub for cross-worker SSE | 1, 3 |
| `sse-starlette` | FastAPI SSE streaming | 3 |
| `react` + `vite` | TMA frontend build | 4 |
| `@telegram-apps/sdk` | Optional typed Telegram WebApp SDK | 4 |

---

Each phase is independently deployable — Phase 1+2 ship value (message cleanup) before needing Redis or React.
