"""
Configuration: env loading, constants, logging, access control.
"""

import logging
import logging.handlers
import os
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ──────────────────────────────────────────────
# Telegram
# ──────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
# ──────────────────────────────────────────────
# LLM (OpenAI-compatible: OpenRouter, DashScope, Ollama, etc.)
# ──────────────────────────────────────────────
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen/qwen3-235b-a22b:free")

SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "Ты — полезный AI-ассистент. Отвечай кратко и по делу. Язык ответа — русский, если пользователь не просит иначе.",
)

SUMMARY_PROMPTS = {
    "brief": (
        "Ты — ассистент для создания кратких саммари. "
        "Создай краткое резюме текста в 3-5 предложений. "
        "Выдели только самое важное. Язык ответа — русский."
    ),
    "detailed": (
        "Ты — ассистент для создания подробных саммари. "
        "Создай подробное структурированное резюме текста. "
        "Используй подзаголовки и списки для организации информации. "
        "Охвати все ключевые темы и аргументы. Язык ответа — русский."
    ),
    "keypoints": (
        "Ты — ассистент для извлечения ключевых тезисов. "
        "Извлеки из текста все ключевые тезисы и факты. "
        "Оформи как нумерованный список. Каждый пункт — одно утверждение или факт. "
        "Язык ответа — русский."
    ),
}

MAX_SUMMARY_TEXT = 40000  # truncate transcript for summarization

NOTE_PROMPT = (
    "Ты — ассистент для создания структурированных заметок в формате Obsidian Markdown.\n"
    "Пользователь надиктовал голосовое сообщение. Текст распознан автоматически и может содержать речевые артефакты.\n"
    "Твоя задача:\n"
    "1. Придумай краткий информативный заголовок заметки.\n"
    "2. Предложи 2-5 тематических тегов на русском языке (без #).\n"
    "3. Оформи содержание: убери речевые артефакты (э, ну, вот, повторы), структурируй текст, используй списки или абзацы где уместно.\n\n"
    "Строго следуй формату ответа — начни с TITLE:, затем TAGS:, затем пустая строка и текст:\n"
    "TITLE: <заголовок>\n"
    "TAGS: <тег1, тег2, тег3>\n\n"
    "<текст заметки>\n\n"
    "Начни ответ строго с TITLE: — никаких вступлений до этого."
)

# ──────────────────────────────────────────────
# Whisper (STT)
# ──────────────────────────────────────────────
WHISPER_BACKEND = os.getenv("WHISPER_BACKEND", "local")  # "local" or "groq"
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "medium")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# ──────────────────────────────────────────────
# Google Docs (optional)
# ──────────────────────────────────────────────
GDOCS_CREDENTIALS_FILE = os.getenv("GDOCS_CREDENTIALS_FILE", "")
GDOCS_DOCUMENT_ID = os.getenv("GDOCS_DOCUMENT_ID", "")

# ──────────────────────────────────────────────
# Obsidian vault (optional)
# ──────────────────────────────────────────────
OBSIDIAN_VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH", "")
OBSIDIAN_INBOX_FOLDER = os.getenv("OBSIDIAN_INBOX_FOLDER", "Inbox")

# ──────────────────────────────────────────────
# Yandex.Disk WebDAV (optional — overrides local vault if set)
# ──────────────────────────────────────────────
YANDEX_DISK_LOGIN = os.getenv("YANDEX_DISK_LOGIN", "")
YANDEX_DISK_PASSWORD = os.getenv("YANDEX_DISK_PASSWORD", "")
YANDEX_DISK_PATH = os.getenv("YANDEX_DISK_PATH", "ObsidianVault")

# ──────────────────────────────────────────────
# YouTube
# ──────────────────────────────────────────────
YT_MAX_DURATION = int(os.getenv("YT_MAX_DURATION", "7200"))
YT_COOKIES_FILE = os.getenv("YT_COOKIES_FILE", "")
YT_URL_RE = re.compile(
    r'(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([\w-]{11})'
)

# ──────────────────────────────────────────────
# HuggingFace
# ──────────────────────────────────────────────
HF_TOKEN = os.getenv("HF_TOKEN", "")

# ──────────────────────────────────────────────
# Conversation
# ──────────────────────────────────────────────
MAX_HISTORY = 20  # max message pairs to keep

# ──────────────────────────────────────────────
# YouTube cache
# ──────────────────────────────────────────────
YT_CACHE_TTL = 3600  # 1 hour

# ──────────────────────────────────────────────
# Access control
# ──────────────────────────────────────────────
ALLOWED_USERS = os.getenv("ALLOWED_USERS", "")
ALLOWED_USER_IDS: set[int] = set()
if ALLOWED_USERS.strip():
    ALLOWED_USER_IDS = {
        int(uid.strip()) for uid in ALLOWED_USERS.split(",")
        if uid.strip() and uid.strip().lstrip("-").isdigit()
    }

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

_log_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

_log_filename = f"bot_{datetime.now():%Y-%m-%d_%H-%M-%S}.log"
_file_handler = logging.handlers.RotatingFileHandler(
    LOG_DIR / _log_filename, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
_file_handler.setFormatter(_log_fmt)

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_log_fmt)

logging.basicConfig(level=logging.INFO, handlers=[_console_handler, _file_handler])
logger = logging.getLogger("tg_voice")


def is_allowed(user_id: int) -> bool:
    if not ALLOWED_USER_IDS:
        return True
    allowed = user_id in ALLOWED_USER_IDS
    if not allowed:
        logger.warning("Access denied for user_id=%d", user_id)
    return allowed
