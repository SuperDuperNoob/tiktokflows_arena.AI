"""Analytics service for metrics and reporting."""

from typing import Any, Dict, List, Optional

from services.utils.analytics import reconcile as reconcile_fn, build as build_report_fn
from services.utils.db_utils import get_conn, ensure_schema
from services.repositories import AnalyticsRepository
from services.models import GrowthReport, DailySummary
from services.infrastructure.config import get_config
from services.infrastructure.database import Database
from services.infrastructure.logging import get_logger

logger = get_logger(__name__)


class AnalyticsService:
    """Service for analytics and reporting."""

    def __init__(self, db_path: str):
        self.analytics_repo = AnalyticsRepository(db_path)

    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get dashboard analytics data."""
        return {
            "views_today": 0,
            "views_this_week": 0,
            "posts_today": 0,
            "top_products": [],
            "recent_posts": [],
        }

    def generate_ops_report(self, days: int = 3) -> str:
        """Generate OPS report."""
        return "No data available"

    def generate_growth_report(self) -> Dict[str, Any]:
        """Generate growth strategy report."""
        return {
            "analysis": "",
            "recommend_product": "",
            "recommend_sound": "",
            "recommend_hashtag": "",
            "new_captions": [],
        }

    def reconcile_metrics(self) -> Dict[str, Any]:
        """Reconcile local uploads with scraped metrics."""
        return {"matched": 0, "unmatched": 0}

    def get_performance_summary(self, days: int = 7) -> Dict[str, Any]:
        """Get performance summary."""
        return {}

    def run_daily_jobs(self, db: Database, config: dict) -> None:
        """Run daily analytics jobs: scrape, reconcile, growth, report."""
        # Scrape competitor data
        try:
            from competitor_scraper import CompetitorScraper
            scraper = CompetitorScraper(config.get("apify", {}), db)
            summary = scraper.scrape_all()
            logger.info("Scrape complete: %s", summary)
        except Exception as e:
            logger.error("Daily scrape failed: %s", e)

        # Reconcile metrics
        try:
            conn = get_conn()
            ensure_schema(conn)
            stats = reconcile_fn(conn, verbose=False)
            logger.info("Reconcile: %s", stats)
            conn.close()
        except Exception as e:
            logger.error("Reconcile failed: %s", e)

        # Generate report
        try:
            report = build_report_fn(days=3)
            logger.info("Report generated: %s", report[:100] if report else "empty")
        except Exception as e:
            logger.error("Report failed: %s", e)