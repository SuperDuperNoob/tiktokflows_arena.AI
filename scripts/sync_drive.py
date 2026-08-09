"""Sync Drive CLI - thin wrapper for services.core.StorageService

Also provides legacy DriveSyncer class for backward compatibility with tests.
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

logger = logging.getLogger(__name__)


class DriveSyncer:
    """Legacy class for backward compatibility with tests."""

    def __init__(self, config: dict, db=None):
        self.config = config
        self.rclone_remote = config.get("rclone_remote", "gdrive")
        self.remote_path = config.get("remote_path", "TikTokContent")
        self.products_file = config.get("products_file", "content/products.json")
        self.raw_dir = config.get("raw_dir", "content/raw")
        self.min_stock_warning = config.get("min_stock_warning", 5)
        self.service = StorageService()

    def _remote_root(self) -> str:
        """Remote root, consistent with sync_out."""
        base = self.rclone_remote.rstrip(":")
        if self.remote_path:
            return f"{base}:{self.remote_path}"
        return f"{base}:"

    def sync(self):
        """Run full sync pipeline."""
        success, report = self.service.sync_from_drive()
        if success:
            # Build stock report for backward compatibility
            stock_report = {}
            stock_counts = self.service.get_stock_status()
            for product, count in stock_counts.items():
                warning = count < self.min_stock_warning
                stock_report[product] = {
                    "count": count,
                    "files": [],  # Simplified
                    "warning": warning,
                    "product_id": ""  # Not tracked in legacy format
                }
            return True, stock_report
        return False, report


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser(description="Google Drive Sync")
    args = ap.parse_args()

    service = StorageService()
    success, report = service.sync_from_drive()

    if success:
        logger.info("Sync completed: %s", report.get("stats", "ok"))
        return 0
    else:
        logger.error("Sync failed: %s", report.get("error", "unknown"))
        return 1


if __name__ == "__main__":
    sys.exit(main())