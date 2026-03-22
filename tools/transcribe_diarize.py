"""
CLI transcription + speaker diarization tool — uses whisperX.

Pipeline:
    audio → whisperX transcribe → align timestamps → pyannote diarize → labeled transcript

Output format (per segment):
    [00:00:01 - 00:00:05] SPEAKER_00: Hello, how are you?
    [00:00:06 - 00:00:09] SPEAKER_01: I'm doing well, thanks.

Usage:
    python transcribe_diarize.py <audio_file> [audio_file2 ...]
    python transcribe_diarize.py <audio_file> --output result.txt
    python transcribe_diarize.py <audio_file> --min-speakers 2 --max-speakers 4
    python transcribe_diarize.py <audio_file> --no-diarize   # transcribe only, no speakers

Reads from .env:
    WHISPER_MODEL   — model size (default: medium)
    WHISPER_DEVICE  — cuda or cpu (default: cuda)
    HF_TOKEN        — HuggingFace token (required for diarization)

Or pass --hf-token directly.
Each run saves a log to ./logs/diarize_<timestamp>.log
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

LOGS_DIR = Path(__file__).parent.parent / "logs"

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "medium")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")
HF_TOKEN = os.getenv("HF_TOKEN", "")


def setup_logging() -> Path:
    LOGS_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOGS_DIR / f"diarize_{ts}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stderr),
        ],
    )
    return log_file


def fmt_time(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def transcribe_file(
    file_path: str,
    hf_token: str,
    diarize: bool,
    min_speakers: int | None,
    max_speakers: int | None,
    language: str | None,
) -> list[dict]:
    """
    Run whisperX pipeline on a single file.
    Returns list of segments: {start, end, speaker, text}
    """
    import whisperx

    logger = logging.getLogger(__name__)
    compute_type = "float16" if WHISPER_DEVICE == "cuda" else "int8"

    # 1. Load audio
    logger.info("Loading audio: %s", file_path)
    audio = whisperx.load_audio(file_path)

    # 2. Transcribe
    logger.info("Loading whisperX model '%s' on %s...", WHISPER_MODEL, WHISPER_DEVICE)
    model = whisperx.load_model(
        WHISPER_MODEL,
        device=WHISPER_DEVICE,
        compute_type=compute_type,
        language=language,
    )
    logger.info("Transcribing...")
    result = model.transcribe(audio, batch_size=16, language=language)
    detected_lang = result.get("language", language or "en")
    logger.info("Detected language: %s, segments: %d", detected_lang, len(result["segments"]))

    # Free GPU memory
    import gc

    import torch
    del model
    gc.collect()
    if WHISPER_DEVICE == "cuda":
        torch.cuda.empty_cache()

    if not result["segments"]:
        logger.warning("No speech detected in %s", file_path)
        return []

    # 3. Align word timestamps
    logger.info("Loading alignment model for language '%s'...", detected_lang)
    try:
        align_model, metadata = whisperx.load_align_model(
            language_code=detected_lang,
            device=WHISPER_DEVICE,
        )
        logger.info("Aligning timestamps...")
        result = whisperx.align(
            result["segments"],
            align_model,
            metadata,
            audio,
            device=WHISPER_DEVICE,
            return_char_alignments=False,
        )
        del align_model
        gc.collect()
        if WHISPER_DEVICE == "cuda":
            torch.cuda.empty_cache()
    except Exception as e:
        logger.warning("Alignment failed (%s), continuing without word-level timestamps", e)

    if not diarize:
        return [
            {
                "start": seg["start"],
                "end": seg["end"],
                "speaker": None,
                "text": seg["text"].strip(),
            }
            for seg in result["segments"]
        ]

    # 4. Diarize
    if not hf_token:
        logger.error(
            "HF_TOKEN is required for diarization. "
            "Set it in .env or pass --hf-token. "
            "Get a free token at https://huggingface.co/settings/tokens "
            "and accept licenses for pyannote/speaker-diarization-3.1 and pyannote/segmentation-3.0"
        )
        sys.exit(1)

    logger.info("Running speaker diarization...")
    diarize_kwargs: dict = {}
    if min_speakers is not None:
        diarize_kwargs["min_speakers"] = min_speakers
    if max_speakers is not None:
        diarize_kwargs["max_speakers"] = max_speakers

    diarize_model = whisperx.diarize.DiarizationPipeline(
        token=hf_token,
        device=WHISPER_DEVICE,
    )
    diarize_segments = diarize_model(audio, **diarize_kwargs)

    # 5. Assign speakers to segments
    logger.info("Assigning speakers to segments...")
    result = whisperx.assign_word_speakers(diarize_segments, result)

    segments = []
    for seg in result["segments"]:
        segments.append({
            "start": seg["start"],
            "end": seg["end"],
            "speaker": seg.get("speaker", "UNKNOWN"),
            "text": seg["text"].strip(),
        })

    speakers = {s["speaker"] for s in segments}
    logger.info("Done. %d segments, %d speakers: %s", len(segments), len(speakers), sorted(speakers))
    return segments


def format_transcript(segments: list[dict], diarize: bool) -> str:
    lines = []
    for seg in segments:
        ts = f"[{fmt_time(seg['start'])} - {fmt_time(seg['end'])}]"
        if diarize and seg["speaker"]:
            lines.append(f"{ts} {seg['speaker']}: {seg['text']}")
        else:
            lines.append(f"{ts} {seg['text']}")
    return "\n".join(lines)


def main():
    log_file = setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Log: %s", log_file)

    parser = argparse.ArgumentParser(
        description="Transcribe audio/video files with speaker diarization (whisperX + pyannote)"
    )
    parser.add_argument("files", nargs="+", help="Audio/video file(s) to transcribe")
    parser.add_argument("-o", "--output", help="Save transcript to this file")
    parser.add_argument("--hf-token", default=HF_TOKEN, help="HuggingFace token (or set HF_TOKEN in .env)")
    parser.add_argument("--no-diarize", action="store_true", help="Skip diarization, transcribe only")
    parser.add_argument("--min-speakers", type=int, default=None, help="Minimum number of speakers")
    parser.add_argument("--max-speakers", type=int, default=None, help="Maximum number of speakers")
    parser.add_argument("--language", default=None, help="Force language code (e.g. ru, en). Auto-detected if not set.")
    args = parser.parse_args()

    diarize = not args.no_diarize
    results = []

    for file_path in args.files:
        if not Path(file_path).exists():
            logger.error("File not found: %s", file_path)
            continue

        logger.info("Processing: %s", file_path)
        try:
            segments = transcribe_file(
                file_path=file_path,
                hf_token=args.hf_token,
                diarize=diarize,
                min_speakers=args.min_speakers,
                max_speakers=args.max_speakers,
                language=args.language,
            )
        except Exception:
            logger.exception("Failed to process %s", file_path)
            continue

        transcript = format_transcript(segments, diarize)
        results.append((file_path, transcript))
        print(transcript)
        print()

    if args.output and results:
        with open(args.output, "w", encoding="utf-8") as f:
            for file_path, transcript in results:
                if len(results) > 1:
                    f.write(f"# {file_path}\n\n")
                f.write(transcript + "\n\n")
        logger.info("Saved transcript to %s", args.output)


if __name__ == "__main__":
    main()
