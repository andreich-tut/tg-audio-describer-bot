"""
API limits checker for free-tier services: OpenRouter (LLM) and Groq (STT).
"""

import httpx

from config import DEFAULT_LANGUAGE, GROQ_API_KEY, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, WHISPER_BACKEND
from core.i18n import t


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


def format_limits_message(or_data: dict | None, groq_data: dict | None, locale: str = DEFAULT_LANGUAGE) -> str:
    parts = [t("limits.header", locale)]

    # OpenRouter section
    if or_data is None:
        parts.append(t("limits.llm_not_openrouter", locale))
    else:
        usage = or_data.get("usage", 0) or 0
        limit = or_data.get("limit")
        is_free = or_data.get("is_free_tier", False)
        rate = or_data.get("rate_limit") or {}
        tier = t("limits.free_tier", locale) if is_free else t("limits.paid_tier", locale)

        limit_str = f"${limit:.4f}" if limit is not None else t("limits.unlimited", locale)
        parts.append(
            t(
                "limits.llm_openrouter",
                locale,
                model=LLM_MODEL,
                tier=tier,
                usage=f"{usage:.4f}",
                limit=limit_str,
            )
        )
        if rate:
            parts.append(t("limits.rate_limit", locale, requests=rate.get("requests"), interval=rate.get("interval")))

    # Groq section
    if groq_data is None:
        if WHISPER_BACKEND == "groq":
            parts.append(t("limits.groq_not_configured", locale))
        # else: Groq not in use, skip silently
    else:
        lim_r = groq_data.get("limit_req", "?")
        rem_r = groq_data.get("remaining_req", "?")
        rst_r = groq_data.get("reset_req", "")
        lim_t = groq_data.get("limit_tokens", "?")
        rem_t = groq_data.get("remaining_tokens", "?")
        rst_t = groq_data.get("reset_tokens", "")

        active = t("limits.groq_active", locale) if WHISPER_BACKEND == "groq" else t("limits.groq_not_active", locale)
        parts.append(t("limits.groq_header", locale) + active)
        if lim_r:
            reset_suffix = t("limits.reset_suffix", locale, time=rst_r) if rst_r else ""
            parts.append(t("limits.groq_requests", locale, remaining=rem_r, limit=lim_r, reset=reset_suffix))
        if lim_t:
            reset_suffix = t("limits.reset_suffix", locale, time=rst_t) if rst_t else ""
            parts.append(t("limits.groq_tokens", locale, remaining=rem_t, limit=lim_t, reset=reset_suffix))

    return "\n".join(parts)
