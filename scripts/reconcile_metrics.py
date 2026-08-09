"""Reconcile Metrics CLI - thin wrapper for services.core.AnalyticsService"""

import argparse
import logging
import sys
import os

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, SCRIPTS_DIR)

from services.core.analytics_service import AnalyticsService
from services.utils.paths import db_path

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser(description="Reconcile local uploads with scraped metrics")
    ap.add_argument("--days", type=int, default=14,
                    help="lookback window in days (default 14)")
    ap.add_argument("--quiet", action="store_true",
                    help="suppress verbose output")
    args = ap.parse_args()

    service = AnalyticsService(str(db_path()))
    stats = service.reconcile_metrics(window_days=args.days)

    print(f"[reconcile] matched {stats['new_matches']} new | "
          f"linked {stats['linked_total']} total | "
          f"metrics rows {stats['daily_metrics_rows']} | "
          f"unmatched {stats['still_unmatched']}")

    if stats["linked_total"] == 0 and stats["scraped_available"] == 0:
        from services.utils.timezone import OWN_HANDLE
        print(f"[reconcile] NOTE: no scraped videos for @{OWN_HANDLE}. "
              "Ensure the scraper includes your own handle.")

    return 0


if __name__ == "__main__":
    sys.exit(main())