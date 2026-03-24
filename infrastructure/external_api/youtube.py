"""
YouTube: audio download via yt-dlp, diarization helpers.
"""

import asyncio
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path

from shared.config import DEFAULT_LANGUAGE, HF_TOKEN, YT_COOKIES_FILE, YT_MAX_DURATION
from shared.i18n import t

logger = logging.getLogger(__name__)


def _yt_cookie_opts() -> dict:
    """Return yt-dlp auth options based on config."""
    if YT_COOKIES_FILE:
        return {"cookiefile": YT_COOKIES_FILE}
    return {}


def _download_yt_sync(url: str, tmp_dir: str, locale: str = DEFAULT_LANGUAGE) -> tuple[str, str, int]:
    """
    Download audio from YouTube (runs in executor thread).
    Returns (file_path, title, duration_seconds).
    """
    import yt_dlp

    cookie_opts = _yt_cookie_opts()

    # 1. Extract info without downloading to validate
    _common_opts = {
        "quiet": True,
        "no_warnings": True,
        "js_runtimes": {"deno": {}, "node": {}},
        **cookie_opts,
    }
    with yt_dlp.YoutubeDL(_common_opts) as ydl:
        info = ydl.extract_info(url, download=False, process=False)

    duration = info.get("duration") or 0
    title = info.get("title") or "video"
    is_live = info.get("is_live", False)

    if is_live:
        raise ValueError(t("youtube.live_not_supported", locale))
    if duration > YT_MAX_DURATION:
        max_min = YT_MAX_DURATION // 60
        duration_min = duration // 60
        raise ValueError(t("youtube.too_long", locale, duration=duration_min, max_duration=max_min))

    # 2. Download audio only
    outtmpl = os.path.join(tmp_dir, "yt_audio.%(ext)s")
    ydl_opts = {
        **_common_opts,
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": outtmpl,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
            }
        ],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    # Find the downloaded file
    for f in os.listdir(tmp_dir):
        if f.startswith("yt_audio"):
            return os.path.join(tmp_dir, f), title, duration

    raise ValueError(t("youtube.download_failed", locale))


async def download_yt_audio(url: str, locale: str = DEFAULT_LANGUAGE) -> tuple[str, str, int]:
    """Async wrapper: download YouTube audio. Returns (file_path, title, duration)."""
    loop = asyncio.get_event_loop()
    tmp_dir = tempfile.mkdtemp()
    t0 = time.time()
    try:
        result = await loop.run_in_executor(None, _download_yt_sync, url, tmp_dir, locale)
        logger.info("YT download: %.1fs, title=%s, duration=%ds", time.time() - t0, result[1][:60], result[2])
        return result
    except Exception as e:
        logger.error("YT download failed: %s", e)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def wants_diarize(text: str) -> bool:
    """Check if user requested diarization alongside a YouTube URL."""
    lower = text.lower()
    return any(kw in lower for kw in ("diarize", "диариз", "спикеры", "speakers"))


async def transcribe_diarized(file_path: str) -> str:
    """Run whisperX diarization pipeline in a thread. Returns formatted transcript."""
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools"))
    from transcribe_diarize import format_transcript, transcribe_file

    loop = asyncio.get_event_loop()
    segments = await loop.run_in_executor(
        None,
        lambda: transcribe_file(
            file_path=file_path,
            hf_token=HF_TOKEN,
            diarize=True,
            min_speakers=None,
            max_speakers=None,
            language=None,
        ),
    )
    return format_transcript(segments, diarize=True)
