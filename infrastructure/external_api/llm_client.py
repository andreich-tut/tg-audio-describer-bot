"""
LLM: OpenAI-compatible chat (with history) and one-shot summarization.
Works with OpenRouter, Alibaba DashScope, Ollama, or any OpenAI-compatible endpoint.
"""

import asyncio
import logging
import time

import openai

from config import (
    DEFAULT_LANGUAGE,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    MAX_SUMMARY_TEXT,
    NOTE_PROMPT,
    SUMMARY_PROMPTS,
    SYSTEM_PROMPT,
)
from shared.i18n import t
from state import add_to_history, get_history, get_user_setting

logger = logging.getLogger(__name__)

_DEFAULT_HEADERS = {
    "HTTP-Referer": "https://github.com/tg-voice-bot",
    "X-Title": "TG Voice Bot",
}

# Module-level default client (shared credentials)
_default_client = openai.AsyncOpenAI(
    api_key=LLM_API_KEY,
    base_url=LLM_BASE_URL,
    default_headers=_DEFAULT_HEADERS,
)

# Cache of per-credential clients
_clients: dict[tuple[str, str], openai.AsyncOpenAI] = {}


def _get_client(user_id: int = 0) -> openai.AsyncOpenAI:
    """Return a cached AsyncOpenAI client for the user's effective credentials."""
    if not user_id:
        return _default_client
    api_key = get_user_setting(user_id, "llm_api_key")
    base_url = get_user_setting(user_id, "llm_base_url")
    if not api_key and not base_url:
        return _default_client
    api_key = api_key or LLM_API_KEY
    base_url = base_url or LLM_BASE_URL
    cache_key = (api_key, base_url)
    if cache_key not in _clients:
        _clients[cache_key] = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers=_DEFAULT_HEADERS,
        )
    return _clients[cache_key]


def _get_model(user_id: int = 0) -> str:
    """Return the effective LLM model for the user."""
    if user_id:
        return get_user_setting(user_id, "llm_model") or LLM_MODEL
    return LLM_MODEL


async def _chat_with_retry(client: openai.AsyncOpenAI, **kwargs) -> openai.types.chat.ChatCompletion:
    """Call chat.completions.create with exponential backoff on rate limit errors."""
    delays = [5, 15, 30]
    for attempt, delay in enumerate(delays + [None]):
        try:
            return await client.chat.completions.create(**kwargs)
        except openai.RateLimitError:
            if delay is None:
                raise
            logger.warning(
                t("llm.rate_limit_warning", DEFAULT_LANGUAGE, attempt=attempt + 1, max=len(delays), delay=delay)
            )
            await asyncio.sleep(delay)


async def ask_ollama(user_id: int, user_message: str, locale: str = DEFAULT_LANGUAGE) -> str:
    """Send message to LLM with conversation history, return full response."""
    add_to_history(user_id, "user", user_message)

    logger.info(
        "LLM request: user_id=%d, history_len=%d, input_len=%d", user_id, len(get_history(user_id)), len(user_message)
    )
    t0 = time.time()

    client = _get_client(user_id)
    model = _get_model(user_id)
    msg = await _chat_with_retry(
        client,
        model=model,
        max_tokens=4096,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + get_history(user_id),
    )

    elapsed = time.time() - t0
    assistant_text = msg.choices[0].message.content.strip() if msg.choices else ""
    if not assistant_text:
        assistant_text = t("llm.empty_response", locale)

    logger.info("LLM response: user_id=%d, %.1fs, response_len=%d", user_id, elapsed, len(assistant_text))
    add_to_history(user_id, "assistant", assistant_text)
    return assistant_text


async def summarize_ollama(
    text: str, detail_level: str, title: str = "", locale: str = DEFAULT_LANGUAGE, user_id: int = 0
) -> str:
    """One-shot summarization via LLM. No conversation history."""
    logger.info("Summarize request: detail=%s, title=%s, text_len=%d", detail_level, title[:60], len(text))
    t0 = time.time()
    system_prompt = SUMMARY_PROMPTS.get(detail_level, SUMMARY_PROMPTS["brief"])

    if len(text) > MAX_SUMMARY_TEXT:
        text = text[:MAX_SUMMARY_TEXT] + t("llm.text_truncated", locale)

    user_content = f"Видео: {title}\n\nТекст:\n{text}" if title else text

    client = _get_client(user_id)
    model = _get_model(user_id)
    msg = await _chat_with_retry(
        client,
        model=model,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )

    result = msg.choices[0].message.content.strip() if msg.choices else ""
    elapsed = time.time() - t0
    logger.info("Summarize done: detail=%s, %.1fs, result_len=%d", detail_level, elapsed, len(result))
    return result or t("llm.empty_response", locale)


async def format_note_ollama(text: str, locale: str = DEFAULT_LANGUAGE, user_id: int = 0) -> tuple[str, list[str], str]:
    """Format voice transcription as an Obsidian note via LLM.

    Returns (title, tags, body).
    """
    logger.info("Note format request: text_len=%d", len(text))
    t0 = time.time()

    client = _get_client(user_id)
    model = _get_model(user_id)
    msg = await _chat_with_retry(
        client,
        model=model,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": NOTE_PROMPT},
            {"role": "user", "content": text},
        ],
    )

    result = msg.choices[0].message.content.strip() if msg.choices else ""
    elapsed = time.time() - t0
    logger.info("Note format done: %.1fs, result_len=%d", elapsed, len(result))

    # Parse TITLE:, TAGS:, then body
    title = t("llm.default_note_title", locale)
    tags: list[str] = []
    body_start = 0
    lines = result.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("TITLE:"):
            title = line[6:].strip() or title
        elif line.startswith("TAGS:"):
            raw = line[5:].strip()
            tags = [t.strip().lstrip("#") for t in raw.split(",") if t.strip()]
            body_start = i + 1
            break

    body = "\n".join(lines[body_start:]).strip()
    return title, tags, body


async def ping_llm() -> str:
    """Test LLM API connectivity. Returns model name on success."""
    await _chat_with_retry(
        _default_client,
        model=LLM_MODEL,
        max_tokens=5,
        messages=[{"role": "user", "content": "ping"}],
    )
    return LLM_MODEL
