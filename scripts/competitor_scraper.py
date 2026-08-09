"""Competitor Scraper CLI - thin wrapper for services.infrastructure.CompetitorScraper"""

import argparse
import logging
import sys
import os

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, SCRIPTS_DIR)

from services.infrastructure.competitor_scraper import CompetitorScraper, run_daily_scrape, DEFAULT_ACTOR
from services.infrastructure.database import Database
from services.infrastructure.config import get_config

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser(description="Competitor Scraper via Apify")
    ap.add_argument("--dry-run", action="store_true",
                    help="skip actual scraping")
    args = ap.parse_args()

    if args.dry_run:
        print("[dry-run] would scrape competitors")
        return 0

    # For CLI use, need config and db
    db = Database(str(get_config()._data.get("logging", {}).get("db_path", "logs/tiktok.db")))
    config = get_config()._data
    result = run_daily_scrape(config.get("apify", {}), db)
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())