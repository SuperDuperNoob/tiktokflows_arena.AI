"""Generate Report CLI - thin wrapper for services.core.AnalyticsService"""

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
from services.utils.db_utils import get_conn, ensure_schema
from services.utils.paths import daily_report as daily_report_path

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser(description="TikTokFlow ops report")
    ap.add_argument("--full", action="store_true",
                    help="also list every individual post with its metrics")
    ap.add_argument("--days", type=int, default=3,
                    help="lookback window in days (default 3)")
    args = ap.parse_args()

    from services.utils.db_utils import get_conn, ensure_schema
    from services.infrastructure.database import Database
    from services.utils.paths import db_path

    db = Database(str(db_path()))
    conn = get_conn()
    ensure_schema(conn)
    conn.close()

    service = AnalyticsService(db.db_path)

    report = service.generate_ops_report(days=args.days)
    print(report)

    try:
        daily_report_path().parent.mkdir(parents=True, exist_ok=True)
        daily_report_path().write_text(report, encoding="utf-8")
    except OSError as e:
        print(f"[report] Could not write daily_report.txt: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())