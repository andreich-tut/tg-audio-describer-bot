import math
import os
import subprocess

INPUT = "./test/oleg-couch.webm"
MAX_MB = 18
MAX_BYTES = MAX_MB * 1024 * 1024
MAX_MINUTES = None  # split by time if set (e.g. 10 = 10 minutes per chunk)


def probe(path):
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration,size",
         "-of", "csv=p=0", path],
        capture_output=True, text=True
    )
    parts = result.stdout.strip().split(",")
    return float(parts[0]), int(parts[1])


def split(input_path, start, duration, output_path):
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(start), "-i", input_path,
        "-t", str(duration), "-c", "copy",
        "-avoid_negative_ts", "make_zero",
        output_path
    ], capture_output=True)


def split_file(input_path, prefix=None, max_minutes=None) -> list[str]:
    input_path = os.path.abspath(input_path)
    src_dir = os.path.dirname(input_path)
    src_stem = os.path.splitext(os.path.basename(input_path))[0]
    src_ext = os.path.splitext(input_path)[1]
    if prefix is None:
        prefix = os.path.join(src_dir, src_stem)

    duration, size = probe(input_path)
    print(f"Duration: {duration:.1f}s | Size: {size/1024/1024:.1f}MB")

    if max_minutes is not None:
        chunk_duration = max_minutes * 60.0
    else:
        chunk_duration = duration * MAX_BYTES / size
    num_chunks = math.ceil(duration / chunk_duration)
    print(f"Chunk duration: {chunk_duration:.1f}s | Estimated chunks: {num_chunks}")

    outputs = []
    idx = 0

    if max_minutes is not None:
        start = 0.0
        while start < duration:
            seg_dur = min(chunk_duration, duration - start)
            out = f"{prefix}_{idx:03d}{src_ext}"
            split(input_path, start, seg_dur, out)
            actual_mb = os.path.getsize(out) / 1024 / 1024
            print(f"  → {out}: {actual_mb:.2f} MB")
            outputs.append(out)
            idx += 1
            start += chunk_duration
    else:
        queue = [(0.0, duration)]
        while queue:
            start, dur = queue.pop(0)
            out = f"{prefix}_{idx:03d}{src_ext}"
            split(input_path, start, dur, out)
            actual = os.path.getsize(out)
            actual_mb = actual / 1024 / 1024
            if actual > MAX_BYTES:
                print(f"  ! {out}: {actual_mb:.2f} MB — too large, re-splitting")
                os.remove(out)
                half = dur / 2
                queue.insert(0, (start + half, dur - half))
                queue.insert(0, (start, half))
            else:
                print(f"  → {out}: {actual_mb:.2f} MB")
                outputs.append(out)
                idx += 1

    return outputs


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", default=INPUT)
    parser.add_argument("--minutes", type=float, default=MAX_MINUTES, help="Max minutes per chunk (default: split by size)")
    parser.add_argument("--prefix", default=None, help="Output filename prefix (default: same dir as input, named after source file)")
    args = parser.parse_args()
    chunks = split_file(args.input, prefix=args.prefix, max_minutes=args.minutes)
    print(f"\nDone: {len(chunks)} chunk(s)")
    for c in chunks:
        print(f"  {c}")
