"""
CLI transcription tool — uses the same Whisper setup as bot.py.

Usage:
    python transcribe_cli.py <audio_file> [audio_file2 ...]
    python transcribe_cli.py <audio_file> --output result.txt

Reads WHISPER_MODEL, WHISPER_DEVICE from .env (same as the bot).
Large files are split automatically before transcription.
Each run saves a log to ./logs/transcribe_<timestamp>.log
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

LOGS_DIR = Path(__file__).parent.parent / "logs"


def setup_logging() -> Path:
    LOGS_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOGS_DIR / f"transcribe_{ts}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stderr),
        ],
        force=True,  # override any handlers already set by imported modules (e.g. bot.py)
    )
    return log_file


sys.path.insert(0, str(Path(__file__).parent.parent))
from infrastructure.external_api.groq_client import transcribe


async def run(files: list[str], output: str | None):
    logger = logging.getLogger(__name__)
    results = []
    for path in files:
        if not Path(path).exists():
            logger.error("File not found: %s", path)
            continue
        logger.info("Transcribing: %s", path)
        text = await transcribe(path)
        results.append((path, text))
        print(text)
        print()

    if output:
        with open(output, "w", encoding="utf-8") as f:
            for path, text in results:
                if len(results) > 1:
                    f.write(f"# {path}\n")
                f.write(text + "\n\n")
        logger.info("Saved transcript to %s", output)


def main():
    log_file = setup_logging()
    logging.getLogger(__name__).info("Log: %s", log_file)

    parser = argparse.ArgumentParser(description="Transcribe audio/video files via Whisper (same model as the bot)")
    parser.add_argument("files", nargs="+", help="Audio/video file(s) to transcribe")
    parser.add_argument("-o", "--output", help="Save transcription to this file")
    args = parser.parse_args()

    asyncio.run(run(args.files, args.output))


if __name__ == "__main__":
    main()
