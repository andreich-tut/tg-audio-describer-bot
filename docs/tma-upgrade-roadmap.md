# Technical Roadmap: TMA & Bot Upgrades (v2.0)

## 1. UI/UX Strategy: TMA vs. Chat Commands

### Feature Split
The strategy ensures the chat remains a zero-friction interface for core tasks while the TMA provides a rich UI for management.

| **Keep in Chat** | **Move to TMA** |
|:---|:---|
| `/start`, `/help`, `/stop`, `/clear` | Full settings management |
| Direct audio/voice upload | Yandex.Disk file browser & OAuth |
| `/mode` quick toggle | Conversation history viewer & management |
| YouTube link auto-processing | Transcription editor (pre-Obsidian save) |
| Text messages — LLM chat | Usage stats & rate limit dashboard |
| | Obsidian note preview & template editor |

### Entry Points & Deep Linking
* **Menu Button**: The primary entry point set via `bot.set_chat_menu_button()`.
* **Inline Buttons**: Added after processing to allow "Edit & Save".
* **Deep Linking**: Use the `startapp` parameter (e.g., `startapp=note_123`) to route users to specific notes. This is more reliable than standard URL paths in the Telegram WebView.
* **`/settings` Command**: Opens the TMA directly instead of inline menus.

---

## 2. Message Management: Tracking & Deletion

### Message Tracking Model
A dedicated table tracks message IDs to facilitate the `/clear` command within Telegram's 48-hour window.

```python
class BotMessage(Base):
    __tablename__ = "bot_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id"), index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger)
    direction: Mapped[str] = mapped_column(String(4))  # "in" (user) or "out" (bot)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
```

### Deletion Strategy (`/clear`)
* **Rate Limiting**: Delete in batches of 25 followed by a 1-second sleep.
* **1:1 Chat Constraint**: In private chats, the bot cannot delete user messages. The logic will target bot responses ("out") and ignore user messages ("in") to prevent API errors.
* **48h Limit**: Telegram API only allows deletion for messages sent within the last 48 hours.
* **Database Hygiene**: A background task should delete `BotMessage` records where `created_at < now - 48h` to maintain performance.

---

## 3. Real-time OAuth Sync (Redis-backed SSE)

To support multiple backend workers, the synchronization logic uses Redis Pub/Sub for cross-process communication.

### Architecture
1. **TMA** opens an SSE connection: `GET /api/v1/oauth/events?auth={initData}`.
2. **Backend Worker** subscribes to a Redis channel: `oauth_updates:{user_id}`.
3. **OAuth Callback** (on any worker) publishes to that channel once the token is stored.
4. **SSE Stream** pushes the event to the TMA immediately.

### Frontend Resilience
* **Primary**: Server-Sent Events (SSE) for instant UI updates.
* **Fallback**: `visibilitychange` listener re-fetches state if the user returns to the app and the SSE connection was dropped.

---

## 4. Implementation Priority

| Phase | Feature | Complexity | Dependency |
|:---|:---|:---|:---|
| **1** | **Infrastructure** | Medium | Redis Setup & DB Migration |
| **2** | **Message Deletion** | Low | Tracking Middleware |
| **3** | **Redis SSE** | Medium | `sse-starlette` & Redis Pub/Sub |
| **4** | **Notes Tab (TMA)** | High | React UI & Note Storage Model |
| **5** | **Deep Linking** | Low | `start_param` handling in React |

---

## 5. Security Summary
* **Authentication**: Every TMA request must validate the `initData` HMAC-SHA256 signature.
* **OAuth Binding**: Server-side state tokens bind Yandex redirects to the correct Telegram `user_id`.