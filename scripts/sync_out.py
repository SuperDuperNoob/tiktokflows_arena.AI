"""Sync Out CLI - thin wrapper for services.core.StorageService

Also provides legacy SyncOut class for backward compatibility with tests.
"""

import argparse
import logging
import sys
import os

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, SCRIPTS_DIR)

from services.core.storage_service import StorageService
from services.utils.paths import db_path, drive_root
from services.utils.db_utils import consumed_pending_cleanup, mark_drive_cleaned

logger = logging.getLogger(__name__)


class SyncOut:
    """Legacy class for backward compatibility with tests."""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.rclone_remote = self.config.get("google_drive", {}).get("rclone_remote", "gdrive")
        self.remote_path = (self.config.get("google_drive", {}).get("remote_path", "") or "").strip("/")

    def _remote_root(self) -> str:
        """Remote root, consistent with sync_drive."""
        base = self.rclone_remote.rstrip(":")
        if self.remote_path:
            return f"{base}:{self.remote_path}"
        return f"{base}:"

    def _rclone(self, args: list, timeout: int = 600):
        """Run rclone; returns (ok, message)."""
        import subprocess
        cmd = ["rclone"] + args
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if res.returncode == 0:
                return True, "ok"
            return False, (res.stderr or res.stdout)[-500:]
        except FileNotFoundError:
            return False, "rclone not found — apt install rclone"
        except subprocess.TimeoutExpired:
            return False, "rclone timed out"
        except Exception as e:
            return False, str(e)

    def _delete_remote(self) -> int:
        """Delete Drive copies of consumed raws (from the DB ledger)."""
        pending = consumed_pending_cleanup()
        if not pending:
            return 0

        remote_root = self._remote_root()
        deleted = 0
        from services.utils.paths import drive_cleanup_log
        audit = drive_cleanup_log()
        for row in pending:
            product, filename = row["product_name"], row["filename"]
            remote = f"{remote_root}/{product}/{filename}"
            ok, msg = self._rclone(["deletefile", remote, "--log-level", "INFO"])
            if ok:
                from services.utils.db_utils import mark_drive_cleaned
                mark_drive_cleaned(product, filename)
                deleted += 1
                logger.info("sync_out: deleted remote %s", remote)
                try:
                    audit.parent.mkdir(parents=True, exist_ok=True)
                    with open(audit, "a", encoding="utf-8") as a:
                        from services.utils.timezone import utcnow
                        a.write(f"{utcnow()} DELETED {remote}\n")
                except OSError:
                    pass
            else:
                logger.warning("sync_out: could not delete %s: %s (kept for retry)",
                               remote, msg)
        return deleted

    def sync(self) -> dict:
        """Full sync out cycle."""
        # 1. Copy logs
        self._copy_logs()
        # 2. Copy processed
        self._copy_processed()
        # 3. Delete remote
        deleted = self._delete_remote()
        logger.info("sync_out done: deleted %d remote raw(s)", deleted)
        return {"deleted_remote": deleted}

    def _copy_logs(self) -> None:
        """Push small logs/reports back so they survive local disk loss."""
        from services.utils.paths import success_log, failed_log, burn_jsonl, daily_report, growth_report, PROJECT_ROOT
        remote = self._remote_root()
        files = []
        for p in (success_log(), failed_log(), burn_jsonl(),
                  daily_report(), growth_report()):
            if p.exists() and p.stat().st_size > 0:
                files.append(str(p))
        if not files:
            return
        include = [f"--include={os.path.basename(f)}" for f in files]
        include.append("--include=*")
        ok, msg = self._rclone(["copy", str(PROJECT_ROOT), remote,
                                "--transfers", "1"] + include)
        if not ok:
            logger.warning("sync_out: log copy failed: %s", msg)

    def _copy_processed(self) -> None:
        """Back up the processed archive to Drive/processed/."""
        from services.utils.paths import processed_dir
        proc = processed_dir()
        if not proc.exists():
            return
        if not any(proc.rglob(f"*{ext}") for ext in (".mp4", ".mov", ".mkv", ".webm")):
            return
        remote = f"{self._remote_root()}/processed/"
        ok, msg = self._rclone(["copy", str(proc), remote,
                                "--transfers", "1", "--checkers", "2",
                                "--buffer-size", "16M"])
        if not ok:
            logger.warning("sync_out: processed copy failed: %s", msg)


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser(description="Sync Out - push results to Drive")
    args = ap.parse_args()

    sync_out = SyncOut()
    result = sync_out.sync()
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())