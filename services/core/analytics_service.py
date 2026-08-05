"""Analytics service for metrics and reporting."""

from typing import Any, Dict, List, Optional
import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
from competitor_scraper import CompetitorScraper
from reconcile_metrics import reconcile
from generate_report import build as build_report
import lib

from services.repositories import AnalyticsRepository
from services.models import GrowthReport, DailySummary

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Service for analytics and reporting."""

    def __init__(self):
        self.analytics_repo = AnalyticsRepository()

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

    def run_daily_jobs(self, db, config: dict) -> None:
        """Run daily analytics jobs: scrape, reconcile, growth, report."""
        # Scrape competitor data
        try:
            scraper = CompetitorScraper(config.get("apify", {}), db)
            summary = scraper.scrape_all()
            logger.info("Scrape complete: %s", summary)
        except Exception as e:
            logger.error("Daily scrape failed: %s", e)

        # Reconcile metrics
        try:
            conn = lib.get_conn()
            lib.ensure_schema(conn)
            stats = reconcile(conn, verbose=False)
            logger.info("Reconcile: %s", stats)
            conn.close()
        except Exception as e:
            logger.error("Reconcile failed: %s", e)

        # Generate report
        try:
            report = build_report(days=3)
            logger.info("Report generated: %s", report[:100] if report else "empty")
        except Exception as e:
            logger.error("Report failed: %s", e)