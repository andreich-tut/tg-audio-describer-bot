"""
Higher-level LLM operations: ask_ollama, summarize_ollama, format_note_ollama.
"""

import logging
import time

from application.state import add_to_history, get_history
from infrastructure.external_api.llm_client import _chat_with_retry, _get_client, _get_model
from shared.config import DEFAULT_LANGUAGE, MAX_SUMMARY_TEXT, NOTE_PROMPT, SUMMARY_PROMPTS
from shared.i18n import t

logger = logging.getLogger(__name__)


async def ask_ollama(user_id: int, user_message: str, locale: str = DEFAULT_LANGUAGE) -> str:
    """Send message to LLM with conversation history, return full response."""
    add_to_history(user_id, "user", user_message)

    logger.info(
        "LLM request: user_id=%d, history_len=%d, input_len=%d", user_id, len(get_history(user_id)), len(user_message)
    )
    t0 = time.time()

    from shared.config import SYSTEM_PROMPT

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
