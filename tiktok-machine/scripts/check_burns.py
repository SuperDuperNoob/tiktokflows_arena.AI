#!/usr/bin/env python3
"""
check_burns.py - find static-image burns (1-frame mp4s) before they upload.

Port of tiktokflow_vps/scripts/check_burns.py. Scans the upload queue with
ffprobe, quarantines files with fewer than MIN_OUTPUT_FRAMES frames, and can
audit burn_log.jsonl history.

Usage:
  python3 check_burns.py               # scan the upload queue, report only
  python3 check_burns.py --quarantine  # also move bad files out of the queue
  python3 check_burns.py --log         # audit burn_log.jsonl history too
  python3 check_burns.py --path DIR    # scan a specific directory

Exit code is 1 when something bad is found, so it can gate a deploy.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import lib


def frame_count(path: Path) -> int:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-count_packets", "-show_entries", "stream=nb_read_packets",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
        return int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else 0
    except Exception:
        return 0


def duration(path: Path) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
        return float(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else 0.0
    except Exception:
        return 0.0


def scan(folder: Path, quarantine: bool) -> tuple[int, int]:
    if not folder.exists():
        print(f"  (no such directory: {folder})")
        return 0, 0
    clips = sorted(folder.glob("*.mp4"))
    if not clips:
        print(f"  queue is empty: {folder}")
        return 0, 0

    bad = 0
    quarantine_dir = lib.failed_dir()
    for clip in clips:
        n = frame_count(clip)
        d = duration(clip)
        if n and n < lib.MIN_OUTPUT_FRAMES:
            bad += 1
            print(f"  ❌ {clip.name}: {n} frame(s), {d:.2f}s - STATIC IMAGE")
            if quarantine:
                try:
                    quarantine_dir.mkdir(parents=True, exist_ok=True)
                    dest = quarantine_dir / clip.name
                    shutil.move(str(clip), str(dest))
                    for ext in (".json", ".pid", ".txt"):
                        side = clip.with_suffix(ext)
                        if side.exists():
                            shutil.move(str(side), str(quarantine_dir / side.name))
                    print(f"     -> moved to {dest}")
                except OSError as e:
                    print(f"     -> could not move: {e}")
        else:
            print(f"  ✅ {clip.name}: {n} frames, {d:.2f}s")
    return len(clips), bad


def audit_log() -> int:
    path = lib.burn_jsonl()
    if not path.exists():
        print("  (no burn_log.jsonl yet)")
        return 0
    total = with_frames = suspicious = 0
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            total += 1
            if "frames" in e:
                with_frames += 1
                if e["frames"] and e["frames"] < lib.MIN_OUTPUT_FRAMES:
                    suspicious += 1
                    print(f"  ❌ {e.get('timestamp', '?')} {e.get('output_path', '?')}: "
                          f"{e['frames']} frame(s)")
            else:
                d = e.get("duration_s") or 0
                if 0 < d < 1.5:
                    suspicious += 1
                    print(f"  ⚠️  {e.get('timestamp', '?')} {e.get('output_path', '?')}: "
                          f"{d}s, no frame count")
    except OSError as e:
        print(f"  could not read burn log: {e}")
        return 0
    print(f"  {total} burns logged, {with_frames} with frame counts, "
          f"{suspicious} suspicious")
    return suspicious


def main() -> int:
    ap = argparse.ArgumentParser(description="Detect 1-frame (static image) burns")
    ap.add_argument("--quarantine", action="store_true",
                    help="move bad clips out of the upload queue into failed/")
    ap.add_argument("--log", action="store_true", help="also audit burn_log.jsonl")
    ap.add_argument("--path", help="scan this directory instead of the queue")
    args = ap.parse_args()

    if shutil.which("ffprobe") is None:
        print("ffprobe not found - is ffmpeg installed?")
        return 2

    target = Path(args.path) if args.path else lib.queue_dir()
    print(f"Scanning upload queue: {target}")
    total, bad = scan(target, args.quarantine)

    suspicious = 0
    if args.log:
        print("\nAuditing burn history:")
        suspicious = audit_log()

    print()
    if bad:
        print(f"⚠️  {bad}/{total} queued clip(s) are static images.")
        if not args.quarantine:
            print("    Re-run with --quarantine to move them out of the queue.")
    else:
        print(f"✅ No static-image clips in the queue ({total} checked).")
    return 1 if (bad or suspicious) else 0


if __name__ == "__main__":
    sys.exit(main())
