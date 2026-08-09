"""Check Burns CLI - thin wrapper for services.core.VideoService.quality_gate"""

import argparse
import logging
import sys
import os

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, SCRIPTS_DIR)

from services.core.video_service import VideoService
from services.utils.paths import queue_dir, failed_dir, db_path

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser(description="Detect 1-frame (static image) burns")
    ap.add_argument("--quarantine", action="store_true",
                    help="move bad clips out of the upload queue into failed/")
    ap.add_argument("--log", action="store_true", help="also audit burn_log.jsonl")
    ap.add_argument("--path", help="scan this directory instead of the queue")
    args = ap.parse_args()

    if not os.path.exists("/usr/bin/ffprobe"):
        print("ffprobe not found - is ffmpeg installed?")
        return 2

    target = os.path.abspath(args.path) if args.path else queue_dir()
    print(f"Scanning upload queue: {target}")

    service = VideoService(str(db_path()))
    total, bad = service.quality_gate(target, quarantine=args.quarantine)

    print()
    if bad:
        print(f"⚠️  {bad}/{total} queued clip(s) are static images.")
        if not args.quarantine:
            print("    Re-run with --quarantine to move them out of the queue.")
    else:
        print(f"✅ No static-image clips in the queue ({total} checked).")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())