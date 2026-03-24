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

from shared.config import GROQ_API_KEY, WHISPER_BACKEND, WHISPER_DEVICE, WHISPER_MODEL

# Make tools/ importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools"))
from audio_splitter import split_file

logger = logging.getLogger(__name__)

# Load local model only when needed
_whisper = None
if WHISPER_BACKEND == "local":
    from faster_whisper import WhisperModel

    logger.info("Loading Whisper model '%s' on %s...", WHISPER_MODEL, WHISPER_DEVICE)
    _whisper = WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE, compute_type="int8")
    logger.info("Whisper ready.")
else:
    logger.info("STT backend: %s (local model not loaded)", WHISPER_BACKEND)


def _transcribe_local(file_path: str) -> tuple[str, str]:
    logger.info("Calling whisper.transcribe()...")
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


async def _transcribe_groq(file_path: str) -> str:
    import httpx

    from application.state import update_groq_limits

    logger.info("Calling Groq Whisper API for %s...", file_path)
    async with httpx.AsyncClient(timeout=120) as client:
        with open(file_path, "rb") as f:
            response = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                files={"file": (Path(file_path).name, f, "audio/ogg")},
                data={"model": "whisper-large-v3", "language": "ru"},
            )
    if not response.is_success:
        logger.error("Groq API error %d: %s", response.status_code, response.text)
    response.raise_for_status()
    update_groq_limits(response.headers)
    text = response.json()["text"]
    logger.info("Groq transcription done, text_len=%d", len(text))
    return text


async def transcribe(file_path: str) -> str:
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
                text = await _transcribe_groq(chunk)
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
