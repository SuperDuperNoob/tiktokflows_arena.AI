"""Queue counting utilities."""

from pathlib import Path

from services.utils.paths import queue_dir


def queue_count(root: Path | None = None) -> int:
    """Rendered mp4s in the queue that carry a sidecar."""
    root = Path(root) if root else queue_dir()
    if not root.exists():
        return 0
    count = 0
    for f in root.glob("*.mp4"):
        json_side = f.with_suffix(".json")
        pid_side = f.with_suffix(".pid")
        if json_side.exists() or pid_side.exists():
            count += 1
    return count