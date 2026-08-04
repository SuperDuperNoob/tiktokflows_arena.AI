"""
sync_out.py - push results back to Google Drive and delete posted raws remotely.

DB-as-truth design (differs from tiktokflow_vps's deleted.log approach):

The source of truth for "this raw was already posted" is the SQLite ledger
(raw_stock.posted_at, set by video_processor when it archives the raw). This
file is only the COSMETIC half of the loop:

  1. _copy_logs       — push logs + reports back to Drive (small files)
  2. _copy_processed  — back up the processed archive to Drive/processed/
  3. _delete_remote   — read the DB for consumed raws whose Drive copy hasn't
                        been deleted yet, and rclone deletefile each one.

Why DB, not deleted.log: a missed/broken deletefile can never cause a duplicate
upload, because the selector already excludes posted raws via the DB. If a
remote delete fails, the entry just stays in the DB and is retried next run —
the raw is never re-selected, so we never re-post it.

A cleanup audit log (drive_cleanup.log) is still written for your review, but
it is not load-bearing.

Run:  python3 sync_out.py
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

import lib

logger = logging.getLogger(__name__)


class SyncOut:
    """Copy results to Drive and delete already-posted raws remotely."""

    def __init__(self, config: dict | None = None):
        self.config = config if config is not None else lib.config()
        self.rclone_remote = self.config.get("google_drive", {}).get("rclone_remote", "gdrive")
        self.remote_path = (self.config.get("google_drive", {}).get("remote_path", "") or "").strip("/")

    def _remote_root(self) -> str:
        """Remote root, consistent with sync_drive. rclone_remote may be given
        as 'gdrive:' or 'gdrive' — strip any trailing colon so 'gdrive::path'
        can never happen. Both syncs must target the SAME Drive folder."""
        base = self.rclone_remote.rstrip(":")
        if self.remote_path:
            return f"{base}:{self.remote_path}"
        return f"{base}:"

    def _rclone(self, args: list, timeout: int = 600):
        """Run rclone; returns (ok, message)."""
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

    # ------------------------------------------------------------------- 1 ----

    def _copy_logs(self) -> None:
        """Push small logs/reports back so they survive local disk loss."""
        remote = self._remote_root()
        files = []
        for p in (lib.success_log(), lib.failed_log(), lib.burn_jsonl(),
                  lib.daily_report(), lib.growth_report()):
            if p.exists() and p.stat().st_size > 0:
                files.append(str(p))
        if not files:
            return
        include = [f"--include={Path(f).name}" for f in files]
        include.append("--include=*")
        ok, msg = self._rclone(["copy", str(lib.PROJECT_ROOT), remote,
                                "--transfers", "1"] + include)
        if not ok:
            logger.warning("sync_out: log copy failed: %s", msg)

    # ------------------------------------------------------------------- 2 ----

    def _copy_processed(self) -> None:
        """Back up the processed archive to Drive/processed/."""
        proc = lib.processed_dir()
        if not proc.exists():
            return
        if not any(proc.rglob(f"*{ext}") for ext in lib.VIDEO_EXTS):
            return
        remote = f"{self._remote_root()}/processed/"
        ok, msg = self._rclone(["copy", str(proc), remote,
                                "--transfers", "1", "--checkers", "2",
                                "--buffer-size", "16M"])
        if not ok:
            logger.warning("sync_out: processed copy failed: %s", msg)

    # ------------------------------------------------------------------- 3 ----

    def _delete_remote(self) -> int:
        """Delete Drive copies of consumed raws (from the DB ledger).

        Returns the number of remote files deleted. Failures are left in the
        DB (drive_cleaned_at stays NULL) so they are retried next run. Because
        the ledger already excludes these from selection, a failure can never
        cause a duplicate upload.
        """
        pending = lib.consumed_pending_cleanup()
        if not pending:
            return 0

        remote_root = self._remote_root()
        deleted = 0
        audit = lib.drive_cleanup_log()
        for row in pending:
            product, filename = row["product_name"], row["filename"]
            remote = f"{remote_root}/{product}/{filename}"
            ok, msg = self._rclone(["deletefile", remote, "--log-level", "INFO"])
            if ok:
                lib.mark_drive_cleaned(product, filename)
                deleted += 1
                logger.info("sync_out: deleted remote %s", remote)
                try:
                    audit.parent.mkdir(parents=True, exist_ok=True)
                    with open(audit, "a", encoding="utf-8") as a:
                        a.write(f"{lib.utcnow()} DELETED {remote}\n")
                except OSError:
                    pass
            else:
                logger.warning("sync_out: could not delete %s: %s (kept for retry)",
                               remote, msg)
        return deleted

    # ---------------------------------------------------------------- entry ----

    def sync(self) -> dict:
        self._copy_logs()
        self._copy_processed()
        deleted = self._delete_remote()
        logger.info("sync_out done: deleted %d remote raw(s)", deleted)
        return {"deleted_remote": deleted}


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    print(SyncOut().sync())
    return 0


if __name__ == "__main__":
    sys.exit(main())
