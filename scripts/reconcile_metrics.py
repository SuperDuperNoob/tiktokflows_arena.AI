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
from services.infrastructure.database import Database
from services.utils.paths import db_path
from services.utils.db_utils import get_conn, ensure_schema

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser(description="Reconcile local uploads with scraped metrics")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    db = Database(str(os.environ.get("TIKTOK_MACHINE_CONFIG", "config/config.yaml")))
    service = AnalyticsService(db.db_path)

    # The actual reconciliation is done by the service
    # This is a placeholder - the real reconciliation is done by the service
    print("Reconcile metrics - use orchestrator daily job or call service directly")
    return 0


if __name__ == "__main__":
    sys.exit(main())