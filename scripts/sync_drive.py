"""
Google Drive Sync Pipeline

Syncs content from Google Drive to local raw/ directory using rclone.
After sync, reads products.json and updates the SQLite database with
current stock levels.
"""
import os
import json
import subprocess
import logging
from typing import Tuple, List

from db import Database

logger = logging.getLogger(__name__)


class DriveSyncer:
    """Syncs Google Drive content to local storage via rclone."""

    def __init__(self, config: dict, db: Database):
        self.rclone_remote = config.get("rclone_remote", "gdrive")
        self.remote_path = config.get("remote_path", "TikTokContent")
        self.products_file = config.get("products_file", "content/products.json")
        self.raw_dir = config.get("raw_dir", "content/raw")
        self.min_stock_warning = config.get("min_stock_warning", 5)
        self.db = db

        # Ensure raw dir exists
        os.makedirs(self.raw_dir, exist_ok=True)

    def sync(self) -> Tuple[bool, dict]:
        """
        Run full sync pipeline:
        1. rclone sync Google Drive → local raw/
        2. Read products.json
        3. Update SQLite with raw stock counts
        4. Return stock status for Telegram notification

        Returns:
            (success: bool, stock_report: dict)
            stock_report: {product_name: {"count": int, "files": list, "warning": bool}}
        """
        # Step 1: rclone sync
        logger.info("Starting Google Drive sync...")
        success, sync_msg = self._rclone_sync()

        if not success:
            logger.error(f"rclone sync failed: {sync_msg}")
            return False, {}

        logger.info(f"rclone sync completed: {sync_msg}")

        # Step 2: Read products.json
        products = self._load_products()
        if not products:
            logger.warning("No products found in products.json")
            return True, {}

        # Step 3: Inventory raw videos per product
        stock_report = {}
        for product_name in products:
            product_dir = os.path.join(self.raw_dir, product_name)
            video_files = self._list_videos(product_dir)

            # Ensure product directory exists
            os.makedirs(product_dir, exist_ok=True)

            # Update database
            self.db.sync_raw_stock(product_name, video_files)

            count = len(video_files)
            warning = count < self.min_stock_warning

            stock_report[product_name] = {
                "count": count,
                "files": video_files,
                "warning": warning,
                "product_id": products[product_name]
            }

            logger.info(f"Product '{product_name}': {count} raw videos" +
                       (" ⚠️ LOW STOCK" if warning else ""))

        return True, stock_report

    def _remote_root(self) -> str:
        """Remote root, consistent with sync_out. rclone_remote may be given as
        "gdrive:" or "gdrive" — strip any trailing colon so "gdrive::path" can
        never happen. Both sync_in and sync_out MUST resolve to the same Drive
        folder for the anti-duplicate loop to work."""
        base = self.rclone_remote.rstrip(":")
        if self.remote_path:
            return f"{base}:{self.remote_path}"
        return f"{base}:"

    def _rclone_sync(self) -> Tuple[bool, str]:
        """Execute rclone sync command.

        Uses `rclone copy` (NOT `sync`) — pull new/changed raws only, never
        delete local files. Already-posted raws are removed from Drive by
        sync_out.py, so they never come back; deleting locally would risk
        losing raws that are still waiting on Drive.
        """
        remote_full = self._remote_root()

        cmd = [
            "rclone", "copy",
            remote_full,
            self.raw_dir,
            "--transfers", "1",
            "--checkers", "2",
            "--buffer-size", "16M",
            "--retries", "2",
            "--low-level-retries", "3",
            # Never pull archives / temp / outputs back down.
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
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout for large syncs
            )

            if result.returncode == 0:
                # Extract stats line
                stats_line = "sync completed"
                for line in result.stderr.split("\n"):
                    if "Transferred:" in line or "transferred" in line.lower():
                        stats_line = line.strip()
                        break
                return True, stats_line
            else:
                return False, result.stderr[-500:]

        except subprocess.TimeoutExpired:
            return False, "rclone sync timed out (>600s)"
        except FileNotFoundError:
            return False, "rclone not found — please install: apt install rclone"
        except Exception as e:
            return False, str(e)

    def _load_products(self) -> dict:
        """Load products.json mapping."""
        if not os.path.exists(self.products_file):
            logger.error(f"products.json not found at: {self.products_file}")
            return {}

        try:
            with open(self.products_file, "r") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in products.json: {e}")
            return {}

    def _list_videos(self, directory: str) -> List[str]:
        """List video files in a directory."""
        video_extensions = lib.VIDEO_EXTS
        if not os.path.isdir(directory):
            return []

        return sorted([
            f for f in os.listdir(directory)
            if os.path.splitext(f)[1].lower() in video_extensions
            and os.path.isfile(os.path.join(directory, f))
        ])

    def get_stock_status(self) -> dict:
        """Get current stock status from database (without re-syncing)."""
        return self.db.get_raw_stock_counts()

    def check_low_stock(self) -> List[str]:
        """Return list of products with low stock."""
        counts = self.get_stock_status()
        low = []
        for product, count in counts.items():
            if count < self.min_stock_warning:
                low.append(product)
        return low


def run_sync(config: dict, db: Database) -> Tuple[bool, dict]:
    """Module-level convenience function."""
    syncer = DriveSyncer(config, db)
    return syncer.sync()
