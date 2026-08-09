"""Quality constants and checks."""

import os
from services.infrastructure.config import cfg


# A burn below this MB/s is a quality regression. Mirrors process-videos-v4.sh.
MIN_MB_PER_SEC = float(os.environ.get("MIN_MB_PER_SEC") or
                       cfg("encoding", "min_mb_per_sec", default=0.30) or 0.30)

# Fewer frames than this => the burn is a still image, not a video.
MIN_OUTPUT_FRAMES = int(os.environ.get("MIN_OUTPUT_FRAMES") or
                        cfg("encoding", "min_output_frames", default=10) or 10)


# Telegram hard-caps a message at 4096 chars.
TELEGRAM_LIMIT = 3900


def clamp_telegram(text: str, limit: int = TELEGRAM_LIMIT) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    nl = cut.rfind("\n")
    if nl > limit * 0.6:
        cut = cut[:nl]
    return cut.rstrip() + "\n… (truncated)"