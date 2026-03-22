"""
API limits checker for free-tier services: OpenRouter (LLM) and Groq (STT).
"""

import httpx

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, GROQ_API_KEY, WHISPER_BACKEND


async def check_openrouter() -> dict | None:
    """Fetch OpenRouter key info. Returns None if LLM_BASE_URL is not OpenRouter."""
    if "openrouter.ai" not in LLM_BASE_URL:
        return None
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
        )
        resp.raise_for_status()
        return resp.json().get("data", {})


async def check_groq() -> dict | None:
    """Fetch Groq rate-limit headers via a lightweight models list call.
    Returns None if Groq is not configured."""
    if not GROQ_API_KEY:
        return None
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        )
        resp.raise_for_status()
        h = resp.headers
        return {
            "limit_req": h.get("x-ratelimit-limit-requests"),
            "remaining_req": h.get("x-ratelimit-remaining-requests"),
            "reset_req": h.get("x-ratelimit-reset-requests"),
            "limit_tokens": h.get("x-ratelimit-limit-tokens"),
            "remaining_tokens": h.get("x-ratelimit-remaining-tokens"),
            "reset_tokens": h.get("x-ratelimit-reset-tokens"),
        }


def format_limits_message(or_data: dict | None, groq_data: dict | None) -> str:
    parts = ["📊 *Лимиты API*"]

    # OpenRouter section
    if or_data is None:
        parts.append("\n🤖 *LLM*: не OpenRouter (лимиты недоступны)")
    else:
        usage = or_data.get("usage", 0) or 0
        limit = or_data.get("limit")
        is_free = or_data.get("is_free_tier", False)
        rate = or_data.get("rate_limit") or {}
        tier = "Free" if is_free else "Paid"

        limit_str = f"${limit:.4f}" if limit is not None else "без лимита"
        parts.append(
            f"\n🤖 *OpenRouter (LLM)*"
            f"\nМодель: `{LLM_MODEL}`"
            f"\nТариф: {tier}"
            f"\nПотрачено: ${usage:.4f} / {limit_str}"
        )
        if rate:
            parts.append(f"Rate limit: {rate.get('requests')} req/{rate.get('interval')}")

    # Groq section
    if groq_data is None:
        if WHISPER_BACKEND == "groq":
            parts.append("\n🎙 *Groq (STT)*: ошибка при получении данных")
        # else: Groq not in use, skip silently
    else:
        lim_r = groq_data.get("limit_req", "?")
        rem_r = groq_data.get("remaining_req", "?")
        rst_r = groq_data.get("reset_req", "")
        lim_t = groq_data.get("limit_tokens", "?")
        rem_t = groq_data.get("remaining_tokens", "?")
        rst_t = groq_data.get("reset_tokens", "")

        active = " (активен)" if WHISPER_BACKEND == "groq" else " (не активен)"
        parts.append(f"\n🎙 *Groq (STT)*{active}")
        if lim_r:
            parts.append(f"Запросы: {rem_r} / {lim_r} осталось" + (f", сброс через {rst_r}" if rst_r else ""))
        if lim_t:
            parts.append(f"Токены: {rem_t} / {lim_t} осталось" + (f", сброс через {rst_t}" if rst_t else ""))

    return "\n".join(parts)
