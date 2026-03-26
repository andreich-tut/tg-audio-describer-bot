"""
Speech-to-text: faster-whisper (local) or Groq Whisper API (cloud).
Controlled by WHISPER_BACKEND env var: "local" (default) or "groq".
"""

import asyncio
import logging
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Coroutine

# Make tools/ importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools"))
from audio_splitter import split_file  # pyright: ignore[reportMissingImports]

from shared.config import GROQ_API_KEY, WARP_PROXY, WHISPER_BACKEND, WHISPER_DEVICE, WHISPER_MODEL

# Type alias for optional status callback (async function accepting a string)
StatusCallback = Callable[[str], Coroutine] | None

logger = logging.getLogger(__name__)

# Load local model only when needed
_whisper = None
if WHISPER_BACKEND == "local":
    from faster_whisper import WhisperModel  # pyright: ignore[reportMissingImports]

    logger.info("Loading Whisper model '%s' on %s...", WHISPER_MODEL, WHISPER_DEVICE)
    _whisper = WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE, compute_type="int8")
    logger.info("Whisper ready.")
else:
    logger.info("STT backend: %s (local model not loaded)", WHISPER_BACKEND)


def _transcribe_local(file_path: str) -> tuple[str, str]:
    logger.info("Calling whisper.transcribe()...")
    if not _whisper:
        raise RuntimeError("Whisper model not loaded")
    segments, info = _whisper.transcribe(
        file_path,
        language="ru",
        beam_size=5,
        vad_filter=True,
    )
    logger.info("Got segments generator, language=%s, duration=%.1fs", info.language, info.duration)
    parts = []
    for i, seg in enumerate(segments):
        logger.info("Segment %d [%.1f-%.1fs]: %s", i, seg.start, seg.end, seg.text[:60])
        parts.append(seg.text.strip())
    logger.info("Transcription done, %d segments", len(parts))
    return " ".join(parts), info.language


WARP_RECONNECT_MAX_RETRIES = 3
WARP_RECONNECT_WAIT = 10  # seconds to wait after reconnect


async def _reconnect_warp() -> bool:
    """Reconnect Cloudflare WARP to cycle the exit IP. Returns True if reconnected."""
    logger.info("Reconnecting WARP to get a new exit IP...")
    try:
        proc = await asyncio.create_subprocess_exec(
            "warp-cli",
            "--accept-tos",
            "disconnect",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        await asyncio.sleep(1)
        proc = await asyncio.create_subprocess_exec(
            "warp-cli",
            "--accept-tos",
            "connect",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

        # Wait for WARP to report Connected
        for _ in range(WARP_RECONNECT_WAIT):
            proc = await asyncio.create_subprocess_exec(
                "warp-cli",
                "--accept-tos",
                "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            if b"Connected" in stdout:
                logger.info("WARP reconnected successfully.")
                return True
            await asyncio.sleep(1)
        logger.error("WARP failed to reconnect within %ds", WARP_RECONNECT_WAIT)
        return False
    except Exception:
        logger.exception("WARP reconnect failed")
        return False


async def _transcribe_groq(file_path: str, status_callback: StatusCallback = None) -> str:
    import httpx

    from application.state import update_groq_limits

    logger.info("Calling Groq Whisper API for %s...", file_path)

    last_error = None
    for attempt in range(1 + WARP_RECONNECT_MAX_RETRIES):
        async with httpx.AsyncClient(timeout=120, proxy=WARP_PROXY if WARP_PROXY else None) as client:
            with open(file_path, "rb") as f:
                response = await client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                    files={"file": (Path(file_path).name, f, "audio/ogg")},
                    data={"model": "whisper-large-v3", "language": "ru"},
                )

        if response.status_code == 403 and WARP_PROXY and attempt < WARP_RECONNECT_MAX_RETRIES:
            logger.warning(
                "Groq returned 403 (attempt %d/%d), reconnecting WARP...", attempt + 1, WARP_RECONNECT_MAX_RETRIES
            )
            if status_callback:
                await status_callback("warp_reconnecting")
            reconnected = await _reconnect_warp()
            if not reconnected:
                last_error = response
                break
            continue

        if not response.is_success:
            logger.error("Groq API error %d: %s", response.status_code, response.text)
        response.raise_for_status()
        update_groq_limits(dict(response.headers))
        text = response.json()["text"]
        logger.info("Groq transcription done, text_len=%d", len(text))
        return text

    # All retries exhausted
    if last_error:
        last_error.raise_for_status()
    raise RuntimeError("Groq transcription failed after WARP reconnect retries")


async def transcribe(file_path: str, status_callback: StatusCallback = None) -> str:
    """Transcribe audio file. Backend: WHISPER_BACKEND env var ("local" or "groq")."""
    loop = asyncio.get_event_loop()
    t0 = time.time()
    tmp_dir = tempfile.mkdtemp()
    prefix = os.path.join(tmp_dir, "chunk")
    chunks = await loop.run_in_executor(None, lambda: split_file(file_path, prefix=prefix, max_minutes=5))
    logger.info("STT: split into %d chunks from %s", len(chunks), file_path)
    try:
        texts = []
        if WHISPER_BACKEND == "groq":
            for chunk in chunks:
                text = await _transcribe_groq(chunk, status_callback=status_callback)
                texts.append(text)
        else:
            lang = "ru"
            for chunk in chunks:
                text, lang = await loop.run_in_executor(None, _transcribe_local, chunk)
                texts.append(text)
        full_text = " ".join(t for t in texts if t)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    elapsed = time.time() - t0
    logger.info(
        "STT done: backend=%s, %.1fs, text_len=%d, preview=%s", WHISPER_BACKEND, elapsed, len(full_text), full_text[:80]
    )
    return full_text
