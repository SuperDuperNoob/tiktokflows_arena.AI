"""Path resolution utilities."""

from pathlib import Path
from typing import Optional

from config import cfg as _cfg
from config import get_config


def _get_project_root() -> Path:
    return get_config().project_root


PROJECT_ROOT = _get_project_root()


# Directories under the drive root that are never products.
NON_PRODUCT_DIRS = {
    "soundtrack", "processed", "posted", "failed", "tmp", "VideosDirPath",
    "burn_output", "test_folder", "logs", "archive", "Books",
    "captions", "sounds", "content",
}

# Raw video extensions accepted as INPUT (the burner re-encodes to .mp4 output).
VIDEO_EXTS = {
    ".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi",
    ".flv", ".wmv", ".mpg", ".mpeg", ".m2v",
    ".ts", ".m2ts", ".3gp", ".ogv",
}


def _resolve(p: str) -> Path:
    p = p or ""
    if not p:
        return PROJECT_ROOT
    p = os.path.expanduser(p)
    if not os.path.isabs(p):
        return PROJECT_ROOT / p
    return Path(p)


import os


def env_path(var: str, default: str) -> Path:
    return Path(os.path.expanduser(os.environ.get(var) or default))


def drive_root() -> Path:
    """Root where product video folders live (content/raw in this layout)."""
    return _resolve(_cfg("content", "raw_dir",
                         default=str(PROJECT_ROOT / "content" / "raw")))


def processed_dir() -> Path:
    return _resolve(_cfg("content", "processed_dir",
                         default=str(PROJECT_ROOT / "content" / "processed")))


def failed_dir() -> Path:
    return _resolve(_cfg("content", "failed_dir",
                         default=str(PROJECT_ROOT / "content" / "failed")))


def posted_dir() -> Path:
    return _resolve(_cfg("content", "posted_dir",
                         default=str(PROJECT_ROOT / "content" / "posted")))


def sounds_dir() -> Path:
    return _resolve(_cfg("content", "sounds_dir",
                         default=str(PROJECT_ROOT / "sounds")))


def queue_dir() -> Path:
    """Rendered videos waiting for the uploader. This is the real queue."""
    return _resolve(_cfg("content", "queue_dir",
                         default=str(PROJECT_ROOT / "content" / "processed")))


def db_path() -> Path:
    p = _cfg("logging", "db_path", default=str(PROJECT_ROOT / "logs" / "tiktok.db"))
    return _resolve(p)


def preset_txt() -> Path:
    return _resolve(_cfg("content", "preset_text",
                         default=str(drive_root() / "preset_text.txt")))


def product_txt() -> Path:
    return _resolve(_cfg("content", "product_id_file",
                         default=str(drive_root() / "product_id.txt")))


def burn_jsonl() -> Path:
    return _resolve(_cfg("content", "burn_log",
                         default=str(PROJECT_ROOT / "logs" / "burn_log.jsonl")))


def deleted_log() -> Path:
    return _resolve(_cfg("content", "deleted_log",
                         default=str(PROJECT_ROOT / "logs" / "deleted.log")))


def success_log() -> Path:
    return _resolve(_cfg("content", "success_log",
                         default=str(PROJECT_ROOT / "logs" / "success.log")))


def failed_log() -> Path:
    return _resolve(_cfg("content", "failed_log",
                         default=str(PROJECT_ROOT / "logs" / "failed.log")))


def growth_report() -> Path:
    return _resolve(_cfg("content", "growth_report",
                         default=str(PROJECT_ROOT / "logs" / "growth_report.txt")))


def drive_cleanup_log() -> Path:
    """Audit of remote files deleted by sync_out (review only, not load-bearing)."""
    return _resolve(_cfg("content", "drive_cleanup_log",
                         default=str(PROJECT_ROOT / "logs" / "drive_cleanup.log")))


def daily_report() -> Path:
    return _resolve(_cfg("content", "daily_report",
                         default=str(PROJECT_ROOT / "logs" / "daily_report.txt")))