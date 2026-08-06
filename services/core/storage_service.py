"""Storage service for managing file storage and Google Drive sync."""

from typing import Any, Dict, List, Optional
from pathlib import Path
import subprocess
import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
from config import get_config

from services.utils.legacy import lib

logger = logging.getLogger(__name__)


class StorageService:
    """Service for storage operations - Google Drive sync and local file management."""

    def __init__(self):
        self.config = get_config()

    def sync_from_drive(self) -> tuple[bool, Dict[str, Any]]:
        """Sync raw videos from Google Drive to local content/raw/."""
        rclone_remote = self.config.get("google_drive", "rclone_remote", "")
        remote_path = self.config.get("google_drive", "remote_path", "")
        local_dir = Path(lib.drive_root())

        if not rclone_remote or not remote_path:
            return False, {"error": "Google Drive not configured"}

        remote_full = f"{rclone_remote.rstrip(':')}:{remote_path}" if remote_path else f"{rclone_remote.rstrip(':')}:"

        cmd = [
            "rclone", "copy",
            remote_full,
            str(local_dir),
            "--transfers", "1",
            "--checkers", "2",
            "--buffer-size", "16M",
            "--retries", "2",
            "--low-level-retries", "3",
            "--exclude", "processed/**",
            "--exclude", "failed/**",
            "--exclude", "posted/**",
            "--exclude", "tmp/**",
            "--exclude", "*.lock",
            "--exclude", "burn_log.jsonl",
            "--exclude", "deleted.log",
            "--exclude", "deleted_history.log",
            "--log-level", "INFO",
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode == 0:
                stats_line = "sync completed"
                for line in result.stderr.split("\n"):
                    if "Transferred:" in line or "transferred" in line.lower():
                        stats_line = line.strip()
                        break
                return True, {"stats": stats_line}
            return False, {"error": result.stderr[-500:]}
        except subprocess.TimeoutExpired:
            return False, {"error": "rclone sync timed out (>600s)"}
        except FileNotFoundError:
            return False, {"error": "rclone not found — please install: apt install rclone"}
        except Exception as e:
            return False, {"error": str(e)}

    def sync_to_drive(self) -> tuple[bool, str]:
        """Sync logs and processed videos to Google Drive, then clean up posted raws."""
        rclone_remote = self.config.get("google_drive", "rclone_remote", "")
        remote_path = self.config.get("google_drive", "remote_path", "")

        if not rclone_remote or not remote_path:
            return False, "Google Drive not configured"

        # 1. Copy logs and processed to Drive
        local_logs = Path("logs")
        local_processed = Path("content/processed")
        remote_full = f"{rclone_remote.rstrip(':')}:{remote_path}" if remote_path else f"{rclone_remote.rstrip(':')}"

        # Sync logs
        for local_dir in [local_logs, local_processed]:
            if not local_dir.exists():
                continue
            cmd = [
                "rclone", "copy",
                str(local_dir),
                remote_full,
                "--transfers", "1",
                "--checkers", "2",
                "--buffer-size", "16M",
            ]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
                if result.returncode != 0:
                    return False, f"sync logs/processed failed: {result.stderr[-500:]}"
            except Exception as e:
                return False, f"sync logs/processed error: {e}"

        # 2. Clean up posted raws from Drive (read from DB)
        from services.repositories import Database
        from services.utils.db_utils import consumed_pending_cleanup, mark_drive_cleaned

        db = Database(lib.db_path())
        pending = consumed_pending_cleanup()
        
        for item in pending:
            product = item["product_name"]
            filename = item["filename"]
            remote_file = f"{remote_full}/{product}/{filename}"
            cmd = ["rclone", "deletefile", remote_file, "--log-level", "INFO"]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if result.returncode == 0:
                    mark_drive_cleaned(product, filename)
            except Exception:
                pass  # Non-fatal, will retry next cycle

        return True, "ok"

    def get_stock_status(self) -> Dict[str, int]:
        """Get current stock levels per product."""
        return lib.scan_stock()