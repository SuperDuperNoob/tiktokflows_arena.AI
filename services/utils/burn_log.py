"""Burn log analysis utilities."""

import json
from pathlib import Path
from typing import List, Dict, Optional

from services.utils.paths import burn_jsonl
from services.utils.quality import MIN_OUTPUT_FRAMES


def recent_burns(limit: int = 20, burn_path: Path | None = None) -> List[Dict]:
    path = Path(burn_path) if burn_path else burn_jsonl()
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
    except OSError:
        return []
    out: List[Dict] = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def quality_check(limit: int = 10, burn_path: Path | None = None) -> Optional[Dict]:
    burns = [b for b in recent_burns(limit, burn_path) if b.get("mb_per_sec")]
    if not burns:
        return None
    rates = [float(b["mb_per_sec"]) for b in burns]
    latest = burns[-1]
    bad = [b for b in burns if b.get("low_quality")]
    enc = latest.get("encode") or {}
    frames = latest.get("frames")
    stills = [b for b in burns
              if b.get("frames") is not None and 0 < b["frames"] < MIN_OUTPUT_FRAMES]
    return {
        "count": len(burns),
        "latest_mb_per_sec": float(latest["mb_per_sec"]),
        "latest_kbps": int(latest.get("video_kbps") or 0),
        "avg_mb_per_sec": sum(rates) / len(rates),
        "min_mb_per_sec": min(rates),
        "low_count": len(bad),
        "crf": enc.get("crf"),
        "maxrate": enc.get("maxrate"),
        "degraded": bool(latest.get("low_quality")),
        "frames": frames,
        "duration_s": latest.get("duration_s"),
        "is_still": (None if frames is None
                     else bool(frames and frames < MIN_OUTPUT_FRAMES)),
        "still_count": len(stills),
    }


def audit_burn_log() -> int:
    """Audit burn_log.jsonl for suspicious entries."""
    path = burn_jsonl()
    if not path.exists():
        return 0
    suspicious = 0
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if "frames" in e:
                if e["frames"] and e["frames"] < MIN_OUTPUT_FRAMES:
                    suspicious += 1
            else:
                d = e.get("duration_s") or 0
                if 0 < d < 1.5:
                    suspicious += 1
    except OSError:
        return 0
    return suspicious