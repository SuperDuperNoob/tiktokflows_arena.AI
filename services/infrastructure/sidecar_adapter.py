"""Sidecar adapter for managing sidecar files."""

from typing import Any, Dict, List, Optional
from pathlib import Path
import json


class SidecarAdapter:
    """Adapter for managing sidecar files (.json and .pid)."""

    def __init__(self, queue_dir: Optional[Path] = None):
        self.queue_dir = queue_dir or Path("content/processed")

    def read_json(self, json_path: Path) -> Optional[Dict[str, Any]]:
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def read_pid(self, pid_path: Path) -> Optional[Dict[str, Any]]:
        try:
            txt = pid_path.read_text(encoding="utf-8").strip()
            parts = txt.split("|", 2)
            return {
                "product_id": parts[0] if len(parts) > 0 else "",
                "title": parts[1] if len(parts) > 1 else pid_path.stem,
                "caption": parts[2] if len(parts) > 2 else "",
            }
        except Exception:
            return None

    def read(self, mp4_path: Path) -> Optional[Dict[str, Any]]:
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

    def write(self, mp4_path: Path, metadata: Dict[str, Any]) -> tuple[Path, Path]:
        mp4 = Path(mp4_path)
        json_path, pid_path = self.sidecar_paths(mp4)
        json_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        pid_path.write_text(
            f"{metadata.get('product_id', '')}|{metadata.get('title', '')}|{metadata.get('caption', '')}",
            encoding="utf-8",
        )
        return json_path, pid_path

    def cleanup(self, mp4_path: Path) -> None:
        for ext in (".json", ".pid"):
            side = Path(mp4_path).with_suffix(ext)
            if side.exists():
                side.unlink()

    def find(self) -> List[tuple[Path, Path, Dict[str, Any]]]:
        out = []
        if not self.queue_dir.exists():
            return out
        for mp4 in sorted(self.queue_dir.glob("*.mp4")):
            json_side, pid_side = self.sidecar_paths(mp4)
            data = None
            primary = None
            if json_side.exists():
                data = self.read_json(json_side)
                primary = json_side
            elif pid_side.exists():
                data = self.read_pid(pid_side)
                primary = pid_side
            if data is not None and primary is not None:
                out.append((mp4, primary, data))
        return out