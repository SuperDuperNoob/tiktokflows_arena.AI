"""
sidecar_manager.py - read/write/cleanup metadata sidecars for the upload queue.

A rendered video ships with two sidecars:
  - <name>.json  full metadata dict (product id, title, caption, overlay,
                 sound, encode params, quality, timestamps) for the uploader
                 and the analytics/reconciliation pipeline
  - <name>.pid   legacy one-liner `product_id|title|caption` for any tooling
                 that only knows the old format

The sidecar is the only thing linking a rendered mp4 to its product, so
missing sidecars are handled gracefully: the uploader skips a bare mp4 rather
than post something untraceable.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class SidecarManager:
    """Sidecar I/O scoped to one queue directory."""

    def __init__(self, queue_dir: Path):
        self.queue_dir = Path(queue_dir)

    # ------------------------------------------------------------- read ----

    def read_json(self, json_path: Path) -> dict | None:
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception as e:
            logger.warning("sidecar JSON load failed %s: %s", json_path, e)
            return None

    def read_pid(self, pid_path: Path) -> dict | None:
        """legacy .pid: product_id|title|caption"""
        try:
            txt = pid_path.read_text(encoding="utf-8").strip()
            parts = txt.split("|", 2)
            return {
                "product_id": parts[0] if len(parts) > 0 else "",
                "title": parts[1] if len(parts) > 1 else pid_path.stem,
                "caption": parts[2] if len(parts) > 2 else "",
            }
        except Exception as e:
            logger.warning("pid load failed %s: %s", pid_path, e)
            return None

    def read(self, mp4_path: Path) -> dict | None:
        """Metadata for an mp4: prefer the JSON sidecar, fall back to .pid."""
        mp4 = Path(mp4_path)
        json_side = mp4.with_suffix(".json")
        pid_side = mp4.with_suffix(".pid")
        if json_side.exists():
            return self.read_json(json_side)
        if pid_side.exists():
            return self.read_pid(pid_side)
        return None

    def sidecar_paths(self, mp4_path: Path) -> tuple[Path, Path]:
        mp4 = Path(mp4_path)
        return mp4.with_suffix(".json"), mp4.with_suffix(".pid")

    # ------------------------------------------------------------ write ----

    def write(self, mp4_path: Path, metadata: dict) -> tuple[Path, Path]:
        """Write JSON + legacy pid sidecars for a processed video."""
        mp4 = Path(mp4_path)
        json_path, pid_path = self.sidecar_paths(mp4)
        json_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        pid_path.write_text(
            f"{metadata.get('product_id', '')}|{metadata.get('title', '')}"
            f"|{metadata.get('caption', '')}",
            encoding="utf-8")
        logger.info("Sidecars written: %s, %s", json_path, pid_path)
        return json_path, pid_path

    # ------------------------------------------------------------ cleanup ----

    def cleanup(self, mp4_path: Path) -> None:
        """Remove sidecars for an mp4 (after a successful upload)."""
        for ext in (".json", ".pid"):
            side = Path(mp4_path).with_suffix(ext)
            if side.exists():
                try:
                    side.unlink()
                    logger.info("Cleaned sidecar %s", side)
                except OSError as e:
                    logger.warning("Sidecar delete failed %s: %s", side, e)

    def find(self) -> list[tuple[Path, Path, dict]]:
        """All queued (mp4, json_path, metadata) triples that have a sidecar.

        .pid-only mp4s are returned with json_path = the .pid path and a legacy
        metadata dict so callers have a uniform shape.
        """
        out = []
        if not self.queue_dir.exists():
            return out
        for mp4 in sorted(self.queue_dir.glob("*.mp4")):
            json_side, pid_side = self.sidecar_paths(mp4)
            data = None
            if json_side.exists():
                data = self.read_json(json_side)
                primary = json_side
            elif pid_side.exists():
                data = self.read_pid(pid_side)
                primary = pid_side
            if data is not None:
                out.append((mp4, primary, data))
        return out
