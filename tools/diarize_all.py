"""
Run diarization on all audio chunks in the test/ directory and save combined
transcript to test/source.txt.

Usage:
    python tools/diarize_all.py
    python tools/diarize_all.py --no-diarize
    python tools/diarize_all.py --min-speakers 2 --max-speakers 4
    python tools/diarize_all.py --language ru

Chunks are processed in sorted order. Each chunk's transcript is appended to
test/source.txt, prefixed with the filename as a header.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent.parent
TEST_DIR = ROOT / "test" / "chunks"
OUTPUT_FILE = ROOT / "test" / "source.txt"
LOGS_DIR = ROOT / "logs"

HF_TOKEN = os.getenv("HF_TOKEN", "")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "medium")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")

sys.path.insert(0, str(Path(__file__).parent))
from transcribe_diarize import format_transcript, setup_logging, transcribe_file

AUDIO_EXTENSIONS = {".webm", ".ogg", ".mp3", ".wav", ".m4a", ".mp4", ".mkv", ".flac"}


def main():
    setup_logging()
    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(
        description="Diarize all audio chunks in test/ and save to test/source.txt"
    )
    parser.add_argument("--no-diarize", action="store_true", help="Transcribe only, skip speaker diarization")
    parser.add_argument("--min-speakers", type=int, default=None)
    parser.add_argument("--max-speakers", type=int, default=None)
    parser.add_argument("--language", default=None, help="Force language code (e.g. ru, en)")
    parser.add_argument("--hf-token", default=HF_TOKEN)
    args = parser.parse_args()

    diarize = not args.no_diarize

    chunks = sorted(
        p for p in TEST_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
    )

    if not chunks:
        logger.error("No audio files found in %s", TEST_DIR)
        sys.exit(1)

    logger.info("Found %d chunk(s) in %s", len(chunks), TEST_DIR)
    logger.info("Output → %s", OUTPUT_FILE)

    all_parts: list[str] = []

    for chunk in chunks:
        logger.info("Processing: %s", chunk.name)
        try:
            segments = transcribe_file(
                file_path=str(chunk),
                hf_token=args.hf_token,
                diarize=diarize,
                min_speakers=args.min_speakers,
                max_speakers=args.max_speakers,
                language=args.language,
            )
        except Exception:
            logger.exception("Failed to process %s", chunk.name)
            continue

        transcript = format_transcript(segments, diarize)
        all_parts.append(f"# {chunk.name}\n\n{transcript}")
        logger.info("Done: %s (%d segments)", chunk.name, len(segments))

    OUTPUT_FILE.write_text("\n\n".join(all_parts) + "\n", encoding="utf-8")
    logger.info("Saved %d transcript(s) to %s", len(all_parts), OUTPUT_FILE)


if __name__ == "__main__":
    main()
