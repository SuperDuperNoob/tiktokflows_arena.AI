"""
orchestrator.py - the unified main loop (replaces upload_orchestrator.py).

Coordinates the battle-tested pipeline modules into one autonomous scheduler:
  sync → quality-gate → render → upload → notify, on a 2h ±30min jitter with
  quiet hours 2AM-6AM MYT.

It delegates to the hardened modules instead of calling TiktokAutoUploader /
ffmpeg directly:
  - video_processor.py   renders one overlay burn + writes sidecars
  - uploader.py          uploads one queued video (proxy shorthand + geo-check
                         + strict mode + no-retry-on-dead-proxy)
  - check_burns.py       quality gate that quarantines static-image burns
  - sidecar_manager.py   metadata tracking (.json + .pid)
  - generate_report.py   OPS report (daily_report.txt)
  - ai_growth.py         cached AI growth engine (≤1 paid call/day)
  - reconcile_metrics.py links local uploads to scraped TikTok metrics

Runs as a systemd service. Start: python3 orchestrator.py
"""
from __future__ import annotations

import json
import logging
import os
import random
import signal
import sys
import time
from datetime import datetime, timezone, timedelta

import yaml

# Add scripts dir to path for imports.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import lib
from db import Database
from sync_drive import DriveSyncer
from telegram_bot import TelegramBotInterface

logger = logging.getLogger("orchestrator")

# MYT timezone offset (UTC+8).
MYT_OFFSET = timedelta(hours=8)
MYT = timezone(MYT_OFFSET)


class Orchestrator:
    """Autonomous scheduler for the unified TikTok posting pipeline."""

    def __init__(self, config_path: str):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.project_root = os.path.dirname(os.path.dirname(config_path))
        os.chdir(self.project_root)

        db_path = self.config.get("logging", {}).get("db_path", "logs/tiktok.db")
        if not os.path.isabs(db_path):
            db_path = os.path.join(self.project_root, db_path)
        self.db = Database(db_path)

        self.syncer = DriveSyncer({
            "rclone_remote": self.config.get("google_drive", {}).get("rclone_remote", ""),
            "remote_path": self.config.get("google_drive", {}).get("remote_path", ""),
            "products_file": self.config.get("google_drive", {}).get("products_file", ""),
            "raw_dir": self._content("raw_dir", "content/raw"),
            "min_stock_warning": self._content("min_stock_warning", 5),
        }, self.db)

        # State the Telegram bot drives.
        self.paused = False
        self.force_next_product = None
        self._running = True
        self._last_scrape_date = None

        self.telegram = TelegramBotInterface(
            self.config.get("telegram", {}), self.db, orchestrator=self)

        # Re-read config through lib so the pipeline modules agree on paths.
        lib._CFG = None

    def _content(self, key: str, default):
        content = self.config.get("content", {})
        val = content.get(key, default)
        if isinstance(val, str) and val and not os.path.isabs(val):
            return os.path.join(self.project_root, val)
        return val

    # ------------------------------------------------------------------ run ----

    def run(self):
        logger.info("=" * 60)
        logger.info("TikTok Auto-Posting Machine (unified) starting...")
        logger.info(f"Project root: {self.project_root}")
        logger.info("=" * 60)

        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        self.telegram.start()
        logger.info("Telegram bot started")

        try:
            self._do_sync()
        except Exception as e:
            logger.warning("Initial sync failed: %s", e)

        while self._running:
            if self.paused:
                time.sleep(60)
                continue
            try:
                if self._should_post_now():
                    self._run_cycle()
                else:
                    self._check_daily_jobs()
                    time.sleep(60)
            except Exception as e:
                logger.exception("Cycle error: %s", e)
                self.telegram.notify_warning("fatal", f"Orchestrator error: {e}")
                time.sleep(120)

        logger.info("Orchestrator stopped.")

    def _handle_signal(self, signum, frame):
        logger.info(f"Signal {signum} received - shutting down gracefully")
        self._running = False

    def _should_post_now(self) -> bool:
        now = datetime.now(MYT)
        posting = self.config.get("posting", {})
        hour = now.hour
        qs = posting.get("quiet_hours_start", 2)
        qe = posting.get("quiet_hours_end", 6)
        if qs <= hour < qe:
            return False

        last_post = self.db.get_last_post_time()
        if last_post is None:
            return True
        base = posting.get("interval_minutes", 120)
        jitter = random.uniform(-posting.get("jitter_minutes", 30),
                                posting.get("jitter_minutes", 30))
        required = (base + jitter) * 60
        elapsed = (datetime.now(timezone.utc) - last_post).total_seconds()
        return elapsed >= required

    # -------------------------------------------------------------- cycle ----

    def _do_sync(self):
        try:
            return self.syncer.sync()
        except Exception as e:
            logger.error("Sync failed: %s", e)
            return False, {}

    def _run_cycle(self):
        logger.info("Starting upload cycle...")

        sync_ok, stock_report = self._do_sync()
        if not sync_ok:
            self.telegram.notify_warning("sync", "Google Drive sync failed. Skipping this cycle.")
            return

        # ---- Quality gate: quarantine static-image burns before they upload.
        try:
            from check_burns import scan as scan_burns
            lib.queue_dir().mkdir(parents=True, exist_ok=True)
            scan_burns(lib.queue_dir(), quarantine=True)
        except Exception as e:
            logger.warning("Quality gate failed (continuing): %s", e)

        # ---- Render one video + write sidecars.
        try:
            from video_processor import VideoProcessor
            proc = VideoProcessor(self.config)
            proc.run()
        except Exception as e:
            logger.error("Video render failed: %s", e)
            self.telegram.notify_warning("render", f"Video render failed: {e}")
            return

        # ---- Upload one queued video.
        try:
            from uploader import Uploader
            up = Uploader(self.config)
            rc = up.upload()
        except Exception as e:
            logger.error("Uploader failed: %s", e)
            self.telegram.notify_warning("upload", f"Uploader error: {e}")
            return

        # ---- Notify on the outcome.
        posted_today = self.db.get_posted_count_today()
        target = self.config.get("posting", {}).get("daily_post_target", 7)
        if rc == 0:
            caption = ""
            posted = self.db.get_posts_today()
            if posted:
                caption = posted[0].get("caption_text", "")
            self.telegram.notify_upload_success(
                "video", caption, stock_report or {}, posted_today, target)
            # Sync out: push logs/processed backup up AND delete the posted raw
            # from Drive so the next sync_in never re-downloads/re-uploads it.
            try:
                from sync_out import SyncOut
                SyncOut(self.config).sync()
            except Exception as e:
                logger.warning("sync_out failed (retries next cycle): %s", e)
        else:
            self.telegram.notify_upload_failure(
                "video", "Upload failed after retries", "", will_retry=True)

    # ----------------------------------------------------------- daily jobs ----

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
            from competitor_scraper import CompetitorScraper
            scraper = CompetitorScraper(self.config.get("apify", {}), self.db)
            summary = scraper.scrape_all()
            logger.info("Scrape complete: %s", summary)
        except Exception as e:
            logger.error("Daily scrape failed: %s", e)

        # Close the tracking loop: link our uploads to scraped metrics.
        try:
            from reconcile_metrics import reconcile
            conn = lib.get_conn()
            lib.ensure_schema(conn)
            stats = reconcile(conn, verbose=False)
            logger.info("Reconcile: %s", stats)
            conn.close()
        except Exception as e:
            logger.error("Reconcile failed: %s", e)

        # OPS report (pure data, free) -> daily_report.txt + Telegram.
        try:
            from generate_report import build as build_report
            report = build_report(days=3)
            self.telegram.send_notification(report.replace("\n", "<br/>"))
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
