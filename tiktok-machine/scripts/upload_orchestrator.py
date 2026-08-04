"""
Upload Orchestrator — Main Loop

Coordinates all components of the TikTok Auto-Posting Machine:
- Syncs content from Google Drive
- Transforms videos (FFmpeg)
- Uploads via TiktokAutoUploader with proxy
- Manages scheduling with jitter and quiet hours
- Sends Telegram notifications
- Handles failures and retries

Runs as a systemd service on the VPS.
"""
import os
import sys
import json
import time
import random
import shutil
import signal
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional

# Add scripts dir to path for imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import yaml
from db import Database
from sync_drive import DriveSyncer
from transform_video import VideoTransformer
from compliance_engine import ComplianceEngine
from ai_engine import AIEngine
from competitor_scraper import CompetitorScraper
from telegram_bot import TelegramBotInterface

# MYT timezone offset (UTC+8)
MYT_OFFSET = timedelta(hours=8)
MYT = timezone(MYT_OFFSET)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("orchestrator")


class UploadOrchestrator:
    """Main orchestrator for the TikTok auto-posting pipeline."""

    def __init__(self, config_path: str):
        # Load configuration
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        self.project_root = os.path.dirname(os.path.dirname(config_path))
        os.chdir(self.project_root)

        # Resolve relative paths
        self._resolve_paths()

        # Initialize database
        db_path = self.config["logging"]["db_path"]
        if not os.path.isabs(db_path):
            db_path = os.path.join(self.project_root, db_path)
        self.db = Database(db_path)

        # Initialize components
        self.transformer = VideoTransformer({
            "processed_dir": self.content_config["processed_dir"],
            "sounds_dir": self.content_config["sounds_dir"],
            "failed_dir": self.content_config.get("failed_dir",
                os.path.join(self.project_root, "content", "failed")),
        })
        self.compliance = ComplianceEngine(
            self.config.get("compliance", {}),
            ai_config=self.config.get("ai", {}),
        )
        self.syncer = DriveSyncer({
            "rclone_remote": self.config["google_drive"]["rclone_remote"],
            "remote_path": self.config["google_drive"]["remote_path"],
            "products_file": self.config["google_drive"]["products_file"],
            "raw_dir": self.content_config["raw_dir"],
            "min_stock_warning": self.content_config.get("min_stock_warning", 5),
        }, self.db)

        # Telegram bot
        self.telegram = TelegramBotInterface(
            self.config.get("telegram", {}),
            self.db,
            orchestrator=self
        )

        # State
        self.paused = False
        self.force_next_product = None
        self._running = True
        self._last_scrape_date = None

        # Add TiktokAutoUploader to Python path
        uploader_dir = self.config["tiktok"].get("uploader_dir", "/opt/TiktokAutoUploader")
        if os.path.isdir(uploader_dir):
            sys.path.insert(0, uploader_dir)
            # Load the uploader config
            uploader_config = os.path.join(uploader_dir, "config.txt")
            if os.path.exists(uploader_config):
                from tiktok_uploader.Config import Config as UploaderConfig
                UploaderConfig.load(uploader_config)

    def _resolve_paths(self):
        """Resolve relative config paths to absolute paths."""
        self.content_config = self.config.get("content", {})
        for key in ["raw_dir", "processed_dir", "posted_dir", "sounds_dir", "captions_pool"]:
            val = self.content_config.get(key, "")
            if val and not os.path.isabs(val):
                self.content_config[key] = os.path.join(self.project_root, val)

        # Products file
        products_file = self.config["google_drive"].get("products_file", "content/products.json")
        if not os.path.isabs(products_file):
            self.config["google_drive"]["products_file"] = os.path.join(self.project_root, products_file)

    def run(self):
        """Main entry point — runs the orchestrator loop."""
        logger.info("=" * 60)
        logger.info("TikTok Auto-Posting Machine starting...")
        logger.info(f"Project root: {self.project_root}")
        logger.info("=" * 60)

        # Handle signals for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        # Start Telegram bot
        self.telegram.start()
        logger.info("Telegram bot started")

        # Initial sync
        self._do_sync()

        # Main loop
        try:
            while self._running:
                if self.paused:
                    logger.info("Orchestrator is paused. Checking again in 60s...")
                    time.sleep(60)
                    continue

                # Check if it's time to post
                if self._should_post_now():
                    self._run_upload_cycle()
                else:
                    # Check if daily competitor scrape is due
                    self._check_daily_scrape()

                    # Sleep and check again
                    time.sleep(60)

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        except Exception as e:
            logger.exception(f"Fatal error in orchestrator: {e}")
            self.telegram.notify_warning("fatal", f"Orchestrator crashed: {e}")

        logger.info("Orchestrator stopped.")

    def _handle_signal(self, signum, frame):
        """Handle termination signals."""
        logger.info(f"Signal {signum} received — shutting down gracefully")
        self._running = False

    def _should_post_now(self) -> bool:
        """Determine if we should post right now based on schedule."""
        now_myt = datetime.now(MYT)
        posting = self.config.get("posting", {})

        # Check quiet hours
        hour = now_myt.hour
        quiet_start = posting.get("quiet_hours_start", 2)
        quiet_end = posting.get("quiet_hours_end", 6)

        if quiet_start <= hour < quiet_end:
            return False

        # Check if enough time has passed since last post
        last_post = self.db.get_last_post_time()
        if last_post is None:
            return True

        # Calculate required interval with jitter
        base_interval = posting.get("interval_minutes", 120)
        jitter = random.uniform(
            -posting.get("jitter_minutes", 30),
            posting.get("jitter_minutes", 30)
        )
        required_minutes = base_interval + jitter
        required_seconds = required_minutes * 60

        elapsed = (datetime.now(timezone.utc) - last_post).total_seconds()
        return elapsed >= required_seconds

    def _run_upload_cycle(self):
        """Execute one full upload cycle: sync → select → transform → upload → notify."""
        logger.info("Starting upload cycle...")

        # Step 1: Sync Google Drive
        sync_ok, stock_report = self._do_sync()

        if not sync_ok:
            self.telegram.notify_warning("sync", "Google Drive sync failed. Skipping this cycle.")
            return

        # Step 2: Check cookie age
        self._check_cookie_age()

        # Step 3: Select product and video
        selection = self._select_video()
        if not selection:
            logger.warning("No videos available to upload")
            self.telegram.notify_warning("stock", "No raw videos available for any product!")
            return

        product_name, raw_video_path, raw_stock_id = selection
        product_id = self._get_product_id(product_name)

        # Step 4: Get caption
        caption = self._get_caption(product_name)
        if not caption:
            logger.error(f"No compliance-checked captions available for {product_name}")
            self.telegram.notify_warning("captions", f"No captions available for {product_name}. Use /growth to generate.")
            return

        # Step 5: Verify proxy
        proxy_url = self.config.get("proxy", {}).get("endpoint", "")
        proxy_ip = None

        if self.config.get("proxy", {}).get("verify_ip_before_upload", True):
            proxy_ip = self._verify_proxy(proxy_url)
            if not proxy_ip:
                logger.error("Proxy verification failed — skipping upload")
                self.telegram.notify_warning("proxy", "Proxy verification failed (non-residential IP). Upload skipped. Retrying next cycle.")
                return

        # Step 6: Transform video
        try:
            processed_path, transform_params = self.transformer.transform(
                raw_video_path, product_name, caption, audio_mode="mix"
            )
            logger.info(f"Video transformed: {processed_path}")
        except Exception as e:
            logger.error(f"Video transformation failed: {e}")
            self.db.log_event("UPLOAD_FAIL", f"Transform failed for {product_name}: {e}")
            return

        # Step 7: Create DB record
        post_id = self.db.create_post(
            product_name=product_name,
            product_id=product_id,
            raw_video_path=raw_video_path,
            processed_video_path=processed_path,
            caption_text=caption,
            sound_file=transform_params.get("sound_file"),
            speed_factor=transform_params.get("speed_factor"),
            brightness_shift=transform_params.get("brightness"),
        )
        self.db.update_post_status(post_id, "TRANSFORMING")

        # Step 8: Upload via TiktokAutoUploader
        success = self._do_upload(
            session_user=self.config["tiktok"]["session_username"],
            video_path=processed_path,
            title=caption,
            proxy=proxy_url,
            post_id=post_id,
            proxy_ip=proxy_ip,
        )

        # Step 9: Handle result
        if success:
            # Move to posted/
            posted_dir = self.content_config["posted_dir"]
            os.makedirs(posted_dir, exist_ok=True)
            dest = os.path.join(posted_dir, os.path.basename(processed_path))
            shutil.move(processed_path, dest)

            self.db.update_post_status(post_id, "POSTED", proxy_ip=proxy_ip)
            self.db.mark_raw_video_used(raw_stock_id)
            self.db.log_event("UPLOAD_SUCCESS", f"Posted {product_name}: {caption[:50]}")

            # Mark caption as used
            self._mark_caption_used(caption)

            # Notification
            posts_today = self.db.get_posted_count_today()
            target = self.config["posting"].get("daily_post_target", 7)
            self.telegram.notify_upload_success(
                product_name, caption, stock_report, posts_today, target
            )

            logger.info(f"✅ Upload SUCCESS: {product_name}")
        else:
            self.db.update_post_status(post_id, "FAILED", notes="Upload returned failure")
            self.db.log_event("UPLOAD_FAIL", f"Upload failed for {product_name}")

            # Retry logic
            max_retries = self.config["posting"].get("max_retries", 1)
            retry_delay = self.config["posting"].get("retry_delay_minutes", 15) * 60

            self.telegram.notify_upload_failure(
                product_name, "Upload failed", processed_path, will_retry=True
            )

            logger.info(f"Retrying in {retry_delay}s...")
            time.sleep(retry_delay)

            # Retry once
            retry_success = self._do_upload(
                session_user=self.config["tiktok"]["session_username"],
                video_path=processed_path,
                title=caption,
                proxy=proxy_url,
                post_id=post_id,
                proxy_ip=proxy_ip,
            )

            if retry_success:
                posted_dir = self.content_config["posted_dir"]
                dest = os.path.join(posted_dir, os.path.basename(processed_path))
                shutil.move(processed_path, dest)
                self.db.update_post_status(post_id, "POSTED", proxy_ip=proxy_ip)
                self.db.mark_raw_video_used(raw_stock_id)
                self.db.log_event("UPLOAD_SUCCESS", f"Posted {product_name} (retry): {caption[:50]}")
                self.telegram.notify_upload_success(
                    product_name, caption, stock_report,
                    self.db.get_posted_count_today(),
                    self.config["posting"].get("daily_post_target", 7)
                )
            else:
                self.db.update_post_status(post_id, "FAILED", notes="Failed after retry")
                self.db.log_event("UPLOAD_FAIL", f"Upload failed after retry for {product_name}")
                self.telegram.notify_upload_failure(
                    product_name, "Failed after retry", processed_path, will_retry=False
                )

        # Check low stock warnings
        self._check_low_stock(stock_report)

    def _do_sync(self):
        """Run Google Drive sync."""
        try:
            return self.syncer.sync()
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            return False, {}

    def _select_video(self):
        """Select the next video to upload.
        Returns (product_name, raw_video_path, raw_stock_id) or None.
        """
        # Forced product takes priority
        if self.force_next_product:
            product = self.force_next_product
            self.force_next_product = None
            videos = self.db.get_unused_raw_videos(product)
            if videos:
                v = random.choice(videos)
                path = os.path.join(self.content_config["raw_dir"], product, v["filename"])
                if os.path.exists(path):
                    return product, path, v["id"]
            logger.warning(f"Forced product {product} has no available videos")

        # Normal selection: prioritize least-recently posted, most stock
        products_due = self.db.get_products_due_next()

        for p in products_due:
            product_name = p["product_name"]
            videos = self.db.get_unused_raw_videos(product_name)
            if videos:
                v = random.choice(videos[:5])  # Pick from top 5 least-used
                path = os.path.join(self.content_config["raw_dir"], product_name, v["filename"])
                if os.path.exists(path):
                    return product_name, path, v["id"]

        return None

    def _get_caption(self, product_name: str) -> Optional[str]:
        """Get an available caption for the product."""
        captions = self.db.get_available_captions(product_name, limit=10)
        if not captions:
            return None
        # Pick the least-used one
        caption = captions[0]
        return caption["caption_text"]

    def _mark_caption_used(self, caption_text: str):
        """Mark a caption as used in the pool."""
        with self.db._connect() as conn:
            conn.execute(
                """UPDATE caption_pool SET times_used = times_used + 1, last_used = ?
                   WHERE caption_text = ?""",
                (datetime.now(timezone.utc).isoformat(), caption_text)
            )

    def _get_product_id(self, product_name: str) -> str:
        """Get TikTok product ID from config or products.json."""
        # Try config first
        products_config = self.config.get("products", {})
        if product_name in products_config:
            return products_config[product_name].get("product_id", "")

        # Try products.json
        products_file = self.config["google_drive"].get("products_file", "content/products.json")
        if os.path.exists(products_file):
            with open(products_file, "r") as f:
                products = json.load(f)
                return products.get(product_name, "")

        return ""

    def _verify_proxy(self, proxy_url: str) -> Optional[str]:
        """Verify proxy exit IP is residential and in expected country."""
        import httpx

        if not proxy_url:
            logger.warning("No proxy configured — skipping verification")
            return "no-proxy"

        verify_endpoint = self.config["proxy"].get("verify_endpoint", "https://ipinfo.io/json")
        expected_country = self.config["proxy"].get("expected_country", "MY")
        dc_keywords = self.config["proxy"].get("datacenter_keywords", [])

        try:
            proxies = {"http://": proxy_url, "https://": proxy_url}
            resp = httpx.get(verify_endpoint, proxies=proxies, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            ip = data.get("ip", "unknown")
            country = data.get("country", "")
            org = data.get("org", "")

            logger.info(f"Proxy check: IP={ip}, Country={country}, Org={org}")

            # Check country
            if country != expected_country:
                logger.error(f"Proxy IP is in {country}, expected {expected_country}")
                return None

            # Check for datacenter
            for keyword in dc_keywords:
                if keyword.lower() in org.lower():
                    logger.error(f"Proxy IP appears to be datacenter: {org}")
                    return None

            return ip

        except Exception as e:
            logger.error(f"Proxy verification failed: {e}")
            return None

    def _do_upload(self, session_user: str, video_path: str, title: str,
                   proxy: str, post_id: int, proxy_ip: str = None) -> bool:
        """Execute the actual TikTok upload via TiktokAutoUploader."""
        try:
            from tiktok_uploader import tiktok as tt_uploader

            logger.info(f"Uploading to TikTok: {video_path}")
            logger.info(f"  Caption: {title[:80]}...")
            logger.info(f"  Proxy: {'configured' if proxy else 'none'}")

            self.db.update_post_status(post_id, "POSTING")

            result = tt_uploader.upload_video(
                session_user=session_user,
                video=video_path,
                title=title,
                schedule_time=0,
                allow_comment=1,
                allow_duet=0,
                allow_stitch=0,
                visibility_type=0,
                brand_organic_type=0,
                branded_content_type=0,
                ai_label=0,
                proxy=proxy,
            )

            return bool(result)

        except ImportError:
            logger.error("Cannot import tiktok_uploader — check uploader_dir config")
            self.db.log_event("UPLOAD_FAIL", "tiktok_uploader import failed")
            return False
        except SystemExit as e:
            # TiktokAutoUploader calls sys.exit on cookie errors
            logger.error(f"TiktokAutoUploader called sys.exit: {e}")
            error_msg = str(e) if str(e) else "Cookie/session error"
            if "session" in error_msg.lower() or "cookie" in error_msg.lower() or "not found" in error_msg.lower():
                self.telegram.notify_warning("cookie", f"⚠️ TikTok session error: {error_msg}. Please re-login and update cookies.")
            return False
        except Exception as e:
            logger.error(f"Upload exception: {e}")
            return False

    def _check_cookie_age(self):
        """Check if TikTok cookies are getting stale."""
        max_age_days = self.config["tiktok"].get("cookie_max_age_days", 7)
        session_user = self.config["tiktok"]["session_username"]
        uploader_dir = self.config["tiktok"].get("uploader_dir", "/opt/TiktokAutoUploader")

        cookie_path = os.path.join(uploader_dir, "CookiesDir", f"tiktok_session-{session_user}.cookie")

        if not os.path.exists(cookie_path):
            self.telegram.notify_warning("cookie", f"Cookie file not found: {cookie_path}. Please login.")
            return

        # Check file modification time
        mtime = os.path.getmtime(cookie_path)
        age_days = (time.time() - mtime) / 86400

        if age_days > max_age_days:
            self.telegram.notify_warning(
                "cookie",
                f"TikTok cookies are {age_days:.1f} days old (max: {max_age_days}). "
                f"Please re-login and update cookies.json."
            )
            self.db.log_event("COOKIE_WARNING", f"Cookies are {age_days:.1f} days old")

    def _check_low_stock(self, stock_report: dict):
        """Check for low stock warnings."""
        min_stock = self.content_config.get("min_stock_warning", 5)

        for product, info in stock_report.items():
            count = info.get("count", 0) if isinstance(info, dict) else info
            if count < min_stock:
                self.telegram.notify_warning(
                    "stock_low",
                    f"{product} has only {count} raw videos left. Drop new clips in Drive."
                )
                self.db.log_event("STOCK_LOW", f"{product} has {count} videos remaining")

    def _check_daily_scrape(self):
        """Check if daily competitor scrape is due."""
        now_myt = datetime.now(MYT)
        scrape_hour = self.config.get("apify", {}).get("scrape_schedule_hour", 3)

        today = now_myt.strftime("%Y-%m-%d")

        # Only scrape once per day
        if self._last_scrape_date == today:
            return

        # Check if we're in the right hour window
        if now_myt.hour != scrape_hour:
            return

        logger.info(f"Running daily competitor scrape at {now_myt.strftime('%H:%M')} MYT")
        self._last_scrape_date = today

        try:
            scraper = CompetitorScraper(self.config.get("apify", {}), self.db)
            summary = scraper.scrape_all()
            logger.info(f"Scrape complete: {summary}")
        except Exception as e:
            logger.error(f"Daily scrape failed: {e}")


def main():
    """Entry point for systemd service."""
    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "config", "config.yaml"
    )

    if not os.path.exists(config_path):
        print(f"ERROR: Config file not found: {config_path}")
        sys.exit(1)

    orchestrator = UploadOrchestrator(config_path)
    orchestrator.run()


if __name__ == "__main__":
    main()
