"""Upload service for managing video uploads to TikTok."""

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import logging
import os
import random
import shutil
import time
import fcntl

import lib
from lib import (check_proxy_exit, env_flag, is_proxy_transport_error,
                 mask_proxy, normalize_proxy_url)
from sidecar_manager import SidecarManager

from services.models import UploadResult
from services.infrastructure.tiktok_adapter import TikTokAdapter
from services.infrastructure.sidecar_adapter import SidecarAdapter

logger = logging.getLogger("upload_service")


class UploadService:
    """Service for managing video uploads to TikTok."""

    def __init__(self):
        self.config = lib.config()
        self.sidecars = SidecarManager(lib.queue_dir())
        self.tiktok_adapter = TikTokAdapter()

        # Proxy configuration
        raw_proxy = lib.cfg("proxy", "endpoint", default="") or ""
        raw_proxy = os.environ.get("TIKTOK_PROXY", raw_proxy).strip()
        if raw_proxy:
            self.proxy_url = normalize_proxy_url(raw_proxy)
            logger.info("Upload proxy: %s (exit IP verified before upload)",
                        mask_proxy(self.proxy_url))
        else:
            logger.warning(
                "Upload proxy: None - posting from VPS datacenter IP, "
                "0-view shadowban risk (set proxy.endpoint to a Malaysian "
                "residential/4G proxy)")
            self.proxy_url = None

        self.strict_mode = env_flag("TIKTOK_PROXY_STRICT",
                                    default=bool(lib.cfg("proxy", "strict_mode", default=True)))
        self.geo_check = env_flag("TIKTOK_PROXY_GEO_CHECK",
                                  default=bool(lib.cfg("proxy", "geo_check", default=True)))

    def check_cookie_expiry(self) -> None:
        """Check if TikTok session cookies are fresh enough."""
        user = lib.cfg("tiktok", "session_username") or "kumpul.shop"
        uploader_dir = lib.cfg("tiktok", "uploader_dir", default="/opt/TiktokAutoUploader")
        candidates = [
            Path(uploader_dir) / "CookiesDir" / f"tiktok_session-{user}.cookie",
            Path(uploader_dir) / "CookiesDir" / f"tiktok_session-{user}",
            Path("CookiesDir") / f"tiktok_session-{user}.cookie",
        ]
        found = None
        for d in candidates:
            if d.exists():
                found = d
                break
        if found is None:
            logger.warning("No cookie files found - upload will likely fail; "
                           "run qr_login.py / import_cookies.py")
            return
        age_hours = (time.time() - found.stat().st_mtime) / 3600
        logger.info("Cookie %s age %.1fh", found.name, age_hours)
        if age_hours > 12:
            logger.warning("Cookie older than 12h (%.1fh) - high risk of "
                           "session expiry, consider re-login", age_hours)
            try:
                with open(lib.failed_log(), "a") as fl:
                    fl.write(f"{datetime.now().isoformat()} WARNING cookie "
                             f"{found.name} age {age_hours:.1f}h - may need re-login\n")
            except OSError:
                pass

    def verify_proxy(self) -> bool:
        """Return True to proceed. Handles strict-mode abort."""
        if not self.proxy_url:
            return True
        if not self.geo_check:
            logger.info("Proxy geo check disabled via proxy.geo_check")
            return True
        geo_ok, detail = check_proxy_exit(self.proxy_url)
        logger.info("Proxy exit check: %s", detail)
        if geo_ok is True:
            logger.info("Proxy exit IP verified: Malaysia residential/mobile line")
            return True
        if geo_ok is False:
            logger.warning("Proxy exit IP is NOT Malaysian residential/mobile - "
                           "uploads through it may be shadowbanned")
            if self.strict_mode:
                logger.error("STRICT: aborting BEFORE upload - a bad exit would "
                             "burn metered proxy GB for a shadowbanned post. "
                             "Fix proxy.endpoint first.")
                try:
                    with open(lib.failed_log(), "a", encoding="utf-8") as ff:
                        ff.write(f"{datetime.now().isoformat()} ABORTED proxy "
                                 f"geo check failed: {detail}\n")
                except OSError:
                    pass
                return False
            return True
        logger.warning("Proxy geo check unavailable, continuing unverified "
                       "(set proxy.geo_check=false to skip)")
        return True

    def process_upload_queue(self) -> UploadResult:
        """Process the next video in the upload queue."""
        # Acquire upload lock
        lockfile = Path("/tmp/tiktok-machine-upload.lock")
        lockfile.parent.mkdir(parents=True, exist_ok=True)
        with open(lockfile, "w") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                logger.info("Another upload in progress, skipping")
                return UploadResult(success=False, error_message="Another upload in progress")

        try:
            cands = self.sidecars.find()
            if not cands:
                logger.info("No video+sidecar found - ensure video_processor ran")
                return UploadResult(success=False, error_message="No video+sidecar found")

            # Pick the newest with a sidecar
            mp4, _primary, sidecar = cands[0]

            product_id = sidecar.get("product_id", "")
            title = sidecar.get("title", "") or sidecar.get("product_folder", "")
            raw_caption = sidecar.get("caption", "") or sidecar.get("product_folder", "")
            safe_caption = (raw_caption or "")[:21].strip() or sidecar.get("product_folder", "")[:21]

            logger.info("Target Video Path: %s", mp4)
            logger.info("Target Product ID: %s", product_id)
            logger.info("Target Title     : %s", title)
            logger.info("Target Caption   : %r -> safe 21char: %r", raw_caption, safe_caption)
            logger.info("Product Folder   : %s", sidecar.get("product_folder"))
            logger.info("Sound            : %s", sidecar.get("sound_name"))
            logger.info("Hashtags         : %s", sidecar.get("hashtags"))
            logger.info("Session User     : %s", lib.OWN_HANDLE)

            if not self.verify_proxy():
                return UploadResult(success=False, error_message="Proxy verification failed")

            # Anti-bot jitter
            delay = random.randint(5, 90)
            logger.info("Anti-bot jitter sleeping %ss before upload...", delay)
            time.sleep(delay)

            session_user = lib.OWN_HANDLE
            products = [{"product_id": product_id, "caption": safe_caption}] if product_id else []
            max_retries = 2
            last_exc = None

            for attempt in range(1, max_retries + 1):
                try:
                    logger.info("Attempt %d/%d uploading %s via=%s",
                                attempt, max_retries, mp4.name,
                                mask_proxy(self.proxy_url) or "direct")
                    success = self.tiktok_adapter.upload_video(
                        session_user=session_user,
                        video=str(mp4),
                        title=title,
                        products=products,
                        proxy=self.proxy_url
                    )
                    if success:
                        logger.info("Upload SUCCESS for %s", mp4.name)
                        self._log_analytics(sidecar)
                        self._cleanup_success(mp4, sidecar, product_id, title)
                        return UploadResult(
                            success=True,
                            video_path=str(mp4),
                            product_name=sidecar.get("product_folder", ""),
                            product_id=product_id,
                            tiktok_video_id=None,  # Could be extracted from adapter
                        )
                    else:
                        logger.error("Upload returned False (TikTok API error) attempt %d", attempt)
                        last_exc = "API returned False"
                        if attempt < max_retries:
                            sleep_t = attempt * 30 + random.randint(5, 15)
                            logger.info("Retrying in %ss...", sleep_t)
                            time.sleep(sleep_t)
                except Exception as e:
                    last_exc = str(e)
                    logger.exception("Exception attempt %d: %s", attempt, e)
                    # Proxy transport failure = proxy dead/wrong; retrying just
                    # re-sends the whole video through it and burns more metered GB.
                    if self.proxy_url and is_proxy_transport_error(e):
                        logger.error("Proxy transport error - NOT retrying to "
                                     "protect metered proxy quota.")
                        break
                    if attempt < max_retries:
                        sleep_t = attempt * 60
                        logger.info("Retry sleep %ss", sleep_t)
                        time.sleep(sleep_t)

            logger.error("All retries failed for %s: %s", mp4.name, last_exc)
            self._move_to_failed(mp4, last_exc)
            return UploadResult(success=False, error_message=last_exc or "All retries failed")

        except Exception as e:
            logger.exception("Upload service error: %s", e)
            return UploadResult(success=False, error_message=str(e))

    def _log_analytics(self, sidecar: dict) -> None:
        """Log upload to analytics database."""
        try:
            from services.repositories import Database
            from services.utils.db_utils import ensure_schema
            conn = Database(lib.db_path())
            ensure_schema(conn.conn)  # type: ignore
            vid_id = (f"{sidecar.get('product_folder', 'unk')}_"
                      f"{int(time.time())}_{random.randint(1000, 9999)}")
            hashtags = json.dumps(sidecar.get("hashtags", []), ensure_ascii=False)
            posted_title = (sidecar.get("title", "") or sidecar.get("caption", "") or "")[:500]
            conn.execute(
                "INSERT OR REPLACE INTO videos(video_id, product_folder, caption, "
                "hashtags_json, sound_id, sound_name, posted_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (vid_id, sidecar.get("product_folder", ""), posted_title, hashtags,
                 sidecar.get("trending_sound_id", "") or sidecar.get("sound_name", ""),
                 sidecar.get("sound_name", ""), datetime.now(timezone.utc).isoformat()))
            conn.commit()
            conn.close()
            logger.info("Logged to analytics DB: %s", vid_id)
        except Exception as e:
            logger.warning("Analytics log failed: %s", e)

    def _cleanup_success(self, mp4: Path, sidecar: dict, product_id: str, title: str) -> None:
        """Clean up after successful upload."""
        try:
            with open(lib.success_log(), "a", encoding="utf-8") as sf:
                sf.write(f"{datetime.now().isoformat()} SUCCESS "
                         f"{mp4.name} product={sidecar.get('product_folder')} "
                         f"pid={product_id} title={title!r} "
                         f"hash={md5_file(mp4)[:10]} "
                         f"size={mp4.stat().st_size}\n")
        except OSError:
            pass

        self.sidecars.cleanup(mp4)
        try:
            mp4.unlink()
            logger.info("Cleaned up after success")
        except OSError:
            pass

    def _move_to_failed(self, mp4: Path, reason: str) -> None:
        """Move failed upload to failed/ directory."""
        lib.failed_dir().mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_dir = lib.failed_dir() / f"{mp4.stem}_{ts}"
        dest_dir.mkdir(exist_ok=True)
        json_side, pid_side = self.sidecars.sidecar_paths(mp4)
        for p in (mp4, json_side, pid_side):
            if p and p.exists():
                try:
                    shutil.move(str(p), str(dest_dir / p.name))
                except OSError as e:
                    logger.warning("Move to failed error %s: %s", p, e)
        try:
            (dest_dir / "reason.txt").write_text(
                f"{datetime.now().isoformat()}\n{reason}\n", encoding="utf-8")
        except OSError:
            pass
        logger.info("Moved failed upload to %s", dest_dir)


def md5_file(p: Path) -> str:
    h = hashlib.md5()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()