"""Rclone adapter for Google Drive sync."""

from typing import Any, Dict, List, Optional
from pathlib import Path
import subprocess
from scripts.config import get_config


class RcloneAdapter:
    """Adapter for rclone operations."""

    def __init__(self):
        self.config = get_config()

    def sync_from_drive(self, remote: str, remote_path: str, local_dir: Path) -> tuple[bool, str]:
        """Sync from Google Drive to local directory."""
        remote_full = f"{remote.rstrip(':')}:{remote_path}" if remote_path else f"{remote.rstrip(':')}:"
        
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
                return True, stats_line
            return False, result.stderr[-500:]
        except subprocess.TimeoutExpired:
            return False, "rclone sync timed out (>600s)"
        except FileNotFoundError:
            return False, "rclone not found — please install: apt install rclone"
        except Exception as e:
            return False, str(e)

    def sync_to_drive(self, local_dir: Path, remote: str, remote_path: str) -> tuple[bool, str]:
        """Sync local directory to Google Drive."""
        remote_full = f"{remote.rstrip(':')}:{remote_path}" if remote_path else f"{remote.rstrip(':')}:"
        
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
            return result.returncode == 0, result.stderr[-500:] if result.returncode != 0 else "ok"
        except Exception as e:
            return False, str(e)

    def delete_from_drive(self, remote: str, remote_path: str, filename: str) -> tuple[bool, str]:
        """Delete a file from Google Drive."""
        remote_full = f"{remote.rstrip(':')}:{remote_path}" if remote_path else f"{remote.rstrip(':')}:"
        remote_file = f"{remote_full}/{filename}"
        
        cmd = ["rclone", "deletefile", remote_file, "--log-level", "INFO"]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return result.returncode == 0, result.stderr[-500:] if result.returncode != 0 else "ok"
        except Exception as e:
            return False, str(e)