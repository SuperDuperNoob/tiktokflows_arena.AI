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
from typing import Optional

import yaml

# Add services and scripts to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICES_DIR = os.path.join(PROJECT_ROOT, "services")
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, SCRIPTS_DIR)

from services.infrastructure.config import get_config, Config
from services.infrastructure.logging import setup_logging, get_logger
from services.core.recovery_manager import RecoveryManager
from services.repositories import Database

logger = get_logger("orchestrator")

# MYT timezone offset (UTC+8).
MYT_OFFSET = timedelta(hours=8)
MYT = timezone(MYT_OFFSET)


class Orchestrator:
    """Autonomous scheduler for the unified TikTok posting pipeline."""

    def __init__(
        self,
        config_path: str,
        video_service: Optional["VideoService"] = None,
        storage_service: Optional["StorageService"] = None,
        upload_service: Optional["UploadService"] = None,
        analytics_service: Optional["AnalyticsService"] = None,
        scheduler_service: Optional["SchedulerService"] = None,
        product_service: Optional["ProductService"] = None,
        proxy_service: Optional["ProxyService"] = None,
    ):
        self.config_path = config_path
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.project_root = os.path.dirname(os.path.dirname(config_path))
        os.chdir(self.project_root)

        # Initialize config
        Config.reset_instance()
        cfg = Config.get_instance(Path(config_path))

        db_path = cfg.get("logging", "db_path", default="logs/tiktok.db")
        if not os.path.isabs(db_path):
            db_path = os.path.join(self.project_root, db_path)

        # Initialize repositories
        self.db = Database(db_path)

        # Initialize services (inject or create defaults)
        from services.core import (
            VideoService, StorageService, UploadService,
            AnalyticsService, SchedulerService,
            ProductService, ProxyService,
        )
        self.video_service = video_service or VideoService(db_path)
        self.storage_service = storage_service or StorageService()
        self.upload_service = upload_service or UploadService()
        self.analytics_service = analytics_service or AnalyticsService(db_path)
        self.scheduler_service = scheduler_service or SchedulerService(db_path)
        self.product_service = product_service or ProductService(db_path)
        self.proxy_service = proxy_service or ProxyService()

        # State the Telegram bot drives.
        self.paused = False
        self.force_next_product = None
        self._running = True
        self._last_scrape_date = None

        # Graceful shutdown state
        self._shutdown_requested = False
        self._shutdown_timeout = 30  # seconds

        # Recovery manager for crash recovery and job reconciliation
        self.recovery_manager = RecoveryManager(self.upload_service.upload_repo)

    def run(self):
        logger.info("=" * 60)
        logger.info("TikTok Auto-Posting Machine (service-oriented) starting...")
        logger.info(f"Project root: {self.project_root}")
        logger.info("=" * 60)

        # Register signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
        # Also handle SIGHUP for config reload
        signal.signal(signal.SIGHUP, self._handle_sighup)

        try:
            self._do_sync()
            # Run startup validation checks
            self._validate_startup()
            # Run startup reconciliation to recover any unfinished jobs
            recon_result = self.recovery_manager.run_startup_reconciliation()
            logger.info("Startup reconciliation result: %s", recon_result)
        except Exception as e:
            logger.warning("Initial sync failed: %s", e)

        while self._running:
            if self.paused:
                time.sleep(60)
                continue
            try:
                if self._shutdown_requested:
                    logger.info("Shutdown requested, exiting main loop")
                    break

                if self.scheduler_service.should_post_now(self.config):
                    self._run_cycle()
                else:
                    self._check_daily_jobs()
                    time.sleep(60)
            except Exception as e:
                logger.exception("Cycle error: %s", e)
                logger.error("Orchestrator error: %s", e)
                time.sleep(120)

        # Graceful shutdown
        self._shutdown()

        logger.info("Orchestrator stopped.")

    def _handle_signal(self, signum, frame):
        logger.info(f"Signal {signum} received - initiating graceful shutdown")
        self._shutdown_requested = True
        self._running = False

    def _handle_sighup(self, signum, frame):
        logger.info("SIGHUP received - reloading configuration")
        try:
            Config.reset_instance()
            cfg = Config.get_instance(Path(self.config_path))
            self.config = cfg.get_section("")
            logger.info("Configuration reloaded successfully")
        except Exception as e:
            logger.error("Failed to reload configuration: %s", e)

    def _validate_startup(self):
        """Validate startup prerequisites."""
        logger.info("Running startup validation checks...")

        # Check database connectivity and schema
        try:
            with self.db._connect() as conn:
                conn.execute("SELECT 1")
            logger.debug("Database connectivity OK")
        except Exception as e:
            raise RuntimeError(f"Database connectivity failed: {e}")

        # Check required directories exist
        from services.utils.paths import drive_root, queue_dir, processed_dir, failed_dir
        for d in [drive_root(), queue_dir(), processed_dir(), failed_dir()]:
            if not d.exists():
                logger.warning("Directory %s does not exist, creating", d)
                d.mkdir(parents=True, exist_ok=True)

        # Check upload queue consistency: no orphaned .mp4 without sidecar
        queue = queue_dir()
        orphaned = 0
        for mp4 in queue.glob("*.mp4"):
            json_side, pid_side = self.upload_service.sidecars.sidecar_paths(mp4)
            if not json_side.exists() and not pid_side.exists():
                logger.warning("Orphaned video file without sidecar: %s", mp4)
                orphaned += 1
        if orphaned:
            logger.warning("Found %d orphaned video files in queue", orphaned)

        # Check processed directory for orphaned files
        processed = processed_dir()
        proc_orphaned = 0
        for mp4 in processed.glob("*.mp4"):
            json_side, pid_side = self.upload_service.sidecars.sidecar_paths(mp4)
            if not json_side.exists() and not pid_side.exists():
                logger.warning("Orphaned processed video without sidecar: %s", mp4)
                proc_orphaned += 1
        if proc_orphaned:
            logger.warning("Found %d orphaned processed videos", proc_orphaned)

        logger.info("Startup validation completed")

    def _shutdown(self):
        """Perform graceful shutdown."""
        logger.info("Starting graceful shutdown...")
        shutdown_start = time.time()

        # 1. Flush any pending logs
        logger.info("Flushing logs...")
        logging.shutdown()

        # 2. Close database connections
        logger.info("Closing database connections...")
        try:
            self.db.close()
            logger.info("Database connections closed")
        except Exception as e:
            logger.error("Error closing database: %s", e)

        # 3. Wait for any in-progress operations (with timeout)
        logger.info("Waiting for in-progress operations to complete...")
        while time.time() - shutdown_start < self._shutdown_timeout:
            # In a real implementation, we'd check for in-progress operations
            # For now, just wait briefly
            time.sleep(0.5)
            break

        logger.info("Graceful shutdown completed in %.1fs", time.time() - shutdown_start)

    def _handle_signal(self, signum, frame):
        logger.info(f"Signal {signum} received - initiating graceful shutdown")
        self._shutdown_requested = True
        self._running = False

    def _handle_sighup(self, signum, frame):
        logger.info("SIGHUP received - reloading configuration")
        try:
            Config.reset_instance()
            cfg = Config.get_instance(Path(self.config_path))
            self.config = cfg.get_section("")
            logger.info("Configuration reloaded successfully")
        except Exception as e:
            logger.error("Failed to reload configuration: %s", e)

    def _shutdown(self):
        """Perform graceful shutdown."""
        logger.info("Starting graceful shutdown...")
        shutdown_start = time.time()

        # 1. Flush any pending logs
        logger.info("Flushing logs...")
        logging.shutdown()

        # 2. Close database connections
        logger.info("Closing database connections...")
        try:
            self.db.close()
            logger.info("Database connections closed")
        except Exception as e:
            logger.error("Error closing database: %s", e)

        # 3. Wait for any in-progress operations (with timeout)
        logger.info("Waiting for in-progress operations to complete...")
        while time.time() - shutdown_start < self._shutdown_timeout:
            # In a real implementation, we'd check for in-progress operations
            # For now, just wait briefly
            time.sleep(0.5)
            break

        logger.info("Graceful shutdown completed in %.1fs", time.time() - shutdown_start)

    def _do_sync(self):
        return self.storage_service.sync_from_drive()

    def _run_cycle(self):
        logger.info("Starting upload cycle...")

        sync_ok, stock_report = self._do_sync()
        if not sync_ok:
            logger.warning("Google Drive sync failed. Skipping this cycle.")
            return

        # Quality gate
        try:
            from services.infrastructure.config import get_config
            cfg = get_config()
            queue_dir = Path(cfg.get("content", "processed_dir", default="content/processed"))
            queue_dir.mkdir(parents=True, exist_ok=True)
            self.video_service.quality_gate(queue_dir, quarantine=True)
        except Exception as e:
            logger.warning("Quality gate failed (continuing): %s", e)

        # Render one video + write sidecars
        try:
            rc = self.video_service.run()
            if rc != 0:
                logger.error("Video render failed with code %s", rc)
                return
        except Exception as e:
            logger.error("Video render failed: %s", e)
            return

        # Upload one queued video
        try:
            upload_result = self.upload_service.process_upload_queue()
            if not upload_result.success:
                logger.error("Upload failed: %s", upload_result.error_message)
                return
            rc = 0
        except Exception as e:
            logger.error("Uploader failed: %s", e)
            return

        # Notify on the outcome (logging for now)
        posted_today = self.db.get_posted_count_today()
        target = self.config.get("posting", {}).get("daily_post_target", 7)
        if rc == 0:
            caption = ""
            posted = self.db.get_posts_today()
            if posted:
                caption = posted[0].get("caption_text", "")
            logger.info("Upload SUCCESS: %s", caption)
            # Sync out
            try:
                sync_ok, _ = self.storage_service.sync_to_drive()
                if not sync_ok:
                    logger.warning("sync_out failed (retries next cycle)")
            except Exception as e:
                logger.warning("sync_out failed (retries next cycle): %s", e)
        else:
            logger.error("Upload failed after retries")

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

        # Use AnalyticsService for daily jobs
        try:
            self.analytics_service.run_daily_jobs(self.db, self.config)
        except Exception as e:
            logger.error("Daily jobs failed: %s", e)


def main():
    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "config", "config.yaml")
    if not os.path.exists(config_path):
        print(f"ERROR: Config file not found: {config_path}")
        sys.exit(1)
    setup_logging()
    Orchestrator(config_path).run()


if __name__ == "__main__":
    main()