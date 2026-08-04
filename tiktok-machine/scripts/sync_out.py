"""
sync_out.py - push results back to Google Drive and remove posted raws remotely.

Port of tiktokflow_vps/scripts/sync_out.sh. This is the half of the sync loop
that prevents duplicate uploads:

  sync_in  pulls NEW raws from Drive -> content/raw/
  burn     archives the posted raw locally to content/processed/ and appends
           its remote-relative path (e.g. "Biocho/foo.mp4") to logs/deleted.log
  sync_out (THIS FILE)
           1. copies logs + reports back to Drive (small files)
           2. copies the processed archive up to Drive/processed/ (backup)
           3. reads deleted.log and `rclone deletefile`s the corresponding
              REMOTE raws, then archives deleted.log -> deleted_history.log
              and clears it

Because the already-posted raw is deleted from Drive, the next sync_in can
never re-download it -> we never re-upload the same video.

Run:  python3 sync_out.py
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

import lib
from db import Database

logger = logging.getLogger(__name__)


class SyncOut:
    """Copy results to Drive and delete already-posted raws remotely."""

    def __init__(self, config: dict | None = None):
        self.config = config if config is not None else lib.config()
        self.rclone_remote = self.config.get("google_drive", {}).get("rclone_remote", "gdrive")
        self.remote_path = (self.config.get("google_drive", {}).get("remote_path", "") or "").strip("/")
        self.db = Database(str(lib.db_path()))

    def _remote_root(self) -> str:
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
        # Include-only copy of the specific files.
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
        if not any(proc.rglob("*.mp4")):
            return
        remote = f"{self._remote_root()}/processed/"
        ok, msg = self._rclone(["copy", str(proc), remote,
                                "--transfers", "1", "--checkers", "2",
                                "--buffer-size", "16M"])
        if not ok:
            logger.warning("sync_out: processed copy failed: %s", msg)

    # ------------------------------------------------------------------- 3 ----

    def _delete_remote_processed(self) -> int:
        """Read deleted.log and delete the matching remote raws.

        Returns the number of remote files deleted. A failed delete is logged
        and the entry is kept (retried next run) so we never lose the mapping.
        """
        dlog = lib.deleted_log()
        if not dlog.exists() or dlog.stat().st_size == 0:
            return 0

        remote_root = self._remote_root()
        lines = [l.strip() for l in dlog.read_text(encoding="utf-8").splitlines() if l.strip()]
        kept, deleted = [], 0
        for rel in lines:
            remote = f"{remote_root}/{rel}"
            ok, msg = self._rclone(["deletefile", remote, "--log-level", "INFO"])
            if ok:
                deleted += 1
                logger.info("sync_out: deleted remote %s", remote)
            else:
                logger.warning("sync_out: could not delete %s: %s", remote, msg)
                kept.append(rel)

        # Archive successfully-processed entries to history; keep failures for retry.
        history = lib.deleted_log().with_name("deleted_history.log")
        done = [l for l in lines if l not in kept]
        if done:
            with open(history, "a", encoding="utf-8") as h:
                h.write("\n".join(done) + "\n")
        with open(dlog, "w", encoding="utf-8") as f:
            f.write("\n".join(kept) + ("\n" if kept else ""))
        return deleted

    # ---------------------------------------------------------------- entry ----

    def sync(self) -> dict:
        self._copy_logs()
        self._copy_processed()
        deleted = self._delete_remote_processed()
        result = {"deleted_remote": deleted}
        logger.info("sync_out done: deleted %d remote raw(s)", deleted)
        return result


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    result = SyncOut().sync()
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
