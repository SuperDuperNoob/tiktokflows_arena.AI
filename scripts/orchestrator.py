"""
orchestrator.py - the unified main loop.

Coordinates the pipeline using the service layer.
"""
from __future__ import annotations

import logging
import os
import random
import signal
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

# Add services and scripts to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICES_DIR = os.path.join(PROJECT_ROOT, "services")
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, SCRIPTS_DIR)

import yaml

from config import get_config
from services.core import (
    UploadService,
    VideoService,
    StorageService,
    ComplianceService,
    CaptionService,
    AnalyticsService,
    SchedulerService,
    NotificationService,
    ProductService,
    ProxyService,
    AIService,
    AuthService,
)
from services.repositories import Database

logger = logging.getLogger("orchestrator")

# MYT timezone offset (UTC+8).
MYT_OFFSET = timedelta(hours=8)
MYT = timezone(MYT_OFFSET)


class Orchestrator:
    """Autonomous scheduler for the unified TikTok posting pipeline."""

    def __init__(self, config_path: str):
        self.config_path = config_path
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.project_root = os.path.dirname(os.path.dirname(config_path))
        os.chdir(self.project_root)

        # Initialize config
        from config import Config
        Config.reset_instance()
        cfg = Config.get_instance(Path(config_path))
        
        db_path = cfg.get("logging", "db_path", default="logs/tiktok.db")
        if not os.path.isabs(db_path):
            db_path = os.path.join(self.project_root, db_path)
        
        # Initialize repositories
        from services.repositories import Database
        self.db = Database(db_path)

        # Initialize services
        self.upload_service = UploadService()
        self.video_service = VideoService()
        self.storage_service = StorageService()
        self.compliance_service = ComplianceService()
        self.caption_service = CaptionService()
        self.analytics_service = AnalyticsService()
        self.scheduler_service = SchedulerService()
        self.notification_service = NotificationService()
        self.product_service = ProductService()
        self.proxy_service = ProxyService()
        self.ai_service = AIService()
        self.auth_service = AuthService()

        # State the Telegram bot drives.
        self.paused = False
        self.force_next_product = None
        self._running = True
        self._last_scrape_date = None

    def run(self):
        logger.info("=" * 60)
        logger.info("TikTok Auto-Posting Machine (service-oriented) starting...")
        logger.info(f"Project root: {self.project_root}")
        logger.info("=" * 60)

        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        try:
            self._do_sync()
        except Exception as e:
            logger.warning("Initial sync failed: %s", e)

        while self._running:
            if self.paused:
                time.sleep(60)
                continue
            try:
                if self.scheduler_service.should_post_now(self.config):
                    self._run_cycle()
                else:
                    self._check_daily_jobs()
                    time.sleep(60)
            except Exception as e:
                logger.exception("Cycle error: %s", e)
                self.notification_service.notify_warning("fatal", f"Orchestrator error: {e}")
                time.sleep(120)

        logger.info("Orchestrator stopped.")

    def _handle_signal(self, signum, frame):
        logger.info(f"Signal {signum} received - shutting down gracefully")
        self._running = False

    def _do_sync(self):
        return self.storage_service.sync_from_drive()

    def _run_cycle(self):
        logger.info("Starting upload cycle...")

        sync_ok, stock_report = self._do_sync()
        if not sync_ok:
            self.notification_service.notify_warning("sync", "Google Drive sync failed. Skipping this cycle.")
            return

        # Quality gate
        try:
            from scripts.check_burns import scan as scan_burns
            from services.config import get_config
            cfg = get_config()
            queue_dir = Path(cfg.get("content", "processed_dir", "content/processed"))
            queue_dir.mkdir(parents=True, exist_ok=True)
            scan_burns(queue_dir, quarantine=True)
        except Exception as e:
            logger.warning("Quality gate failed (continuing): %s", e)

        # Render one video + write sidecars
        try:
            from scripts.video_processor import VideoProcessor
            proc = VideoProcessor(self.config)
            proc.run()
        except Exception as e:
            logger.error("Video render failed: %s", e)
            self.notification_service.notify_warning("render", f"Video render failed: {e}")
            return

        # Upload one queued video
        try:
            from scripts.uploader import Uploader
            up = Uploader(self.config)
            rc = up.upload()
        except Exception as e:
            logger.error("Uploader failed: %s", e)
            self.notification_service.notify_warning("upload", f"Uploader error: {e}")
            return

        # Notify on the outcome
        posted_today = self.db.get_posted_count_today()
        target = self.config.get("posting", {}).get("daily_post_target", 7)
        if rc == 0:
            caption = ""
            posted = self.db.get_posts_today()
            if posted:
                caption = posted[0].get("caption_text", "")
            self.notification_service.notify_upload_success(
                "video", caption, stock_report or {}, posted_today, target)
            # Sync out
            try:
                from scripts.sync_out import SyncOut
                SyncOut(self.config).sync()
            except Exception as e:
                logger.warning("sync_out failed (retries next cycle): %s", e)
        else:
            self.notification_service.notify_upload_failure(
                "video", "Upload failed after retries", "", will_retry=True)

    def _check_daily_jobs(self):
        """Once per MYT day: scrape, reconcile, growth (≤1 AI call), report."""
        now = datetime.now(MYT)
        today = now.strftime("%Y-%m-%d")
        if self._last_scrape_date == today:
            return

        scrape_hour = self.config.get("apify", {}).get("scrape_schedule_hour", 3)
        if now.hour != scrape_hour:
            return

        logger.info("Running daily jobs at %s MYT", now.strftime("%H:%M"))
        self._last_scrape_date = today

        try:
            from scripts.competitor_scraper import CompetitorScraper
            scraper = CompetitorScraper(self.config.get("apify", {}), self.db)
            summary = scraper.scrape_all()
            logger.info("Scrape complete: %s", summary)
        except Exception as e:
            logger.error("Daily scrape failed: %s", e)

        try:
            from scripts.reconcile_metrics import reconcile
            import lib
            conn = lib.get_conn()
            lib.ensure_schema(conn)
            stats = reconcile(conn, verbose=False)
            logger.info("Reconcile: %s", stats)
            conn.close()
        except Exception as e:
            logger.error("Reconcile failed: %s", e)

        try:
            from scripts.generate_report import build as build_report
            report = build_report(days=3)
            # Send via notification service
        except Exception as e:
            logger.error("Report failed: %s", e)


def main():
    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "config", "config.yaml")
    if not os.path.exists(config_path):
        print(f"ERROR: Config file not found: {config_path}")
        sys.exit(1)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    Orchestrator(config_path).run()


if __name__ == "__main__":
    main()