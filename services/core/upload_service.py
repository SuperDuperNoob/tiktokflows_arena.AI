"""Upload service for managing video uploads to TikTok."""

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import random
import shutil
import time
import fcntl

from sidecar_manager import SidecarManager

from services.infrastructure.config import get_config
from services.utils.paths import queue_dir, failed_dir, success_log, db_path
from services.utils.timezone import OWN_HANDLE
from services.utils.proxy import (
    check_proxy_exit,
    is_proxy_transport_error,
    mask_proxy,
    normalize_proxy_url,
)
from services.utils.db_utils import mark_raw_consumed, get_conn, ensure_schema
from services.infrastructure.logging import get_logger
from services.core.metrics_service import metrics
from services.exceptions import UploadError, ProxyError, RetryableError, FatalError
from services.models import UploadResult
from services.models.upload_job import UploadJob, UploadJobStatus
from services.repositories import UploadRepository
from services.infrastructure.tiktok_adapter import TikTokAdapter
from services.infrastructure.sidecar_adapter import SidecarAdapter
from services.core.recovery_manager import RecoveryManager
from services.infrastructure.retry import retry_with_policy, UPLOAD_POLICY

logger = get_logger("upload_service")


def env_flag(name: str, default: bool = False) -> bool:
    """Read environment variable as boolean flag."""
    val = os.environ.get(name, "").strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default


class UploadService:
    """Service for managing video uploads to TikTok."""

    def __init__(self):
        self.config = get_config()
        self.sidecars = SidecarManager(queue_dir())
        self.upload_repo = UploadRepository(db_path())
        self.recovery_manager = RecoveryManager(self.upload_repo)

        # Proxy configuration
        raw_proxy = get_config().get("proxy", "endpoint", default="") or ""
        raw_proxy = os.environ.get("TIKTOK_PROXY", raw_proxy).strip()
        if raw_proxy:
            self.proxy_url = normalize_proxy_url(raw_proxy)
            logger.info("Upload proxy: %s (exit IP verified before upload)",
                        mask_proxy(self.proxy_url or ""))
        else:
            logger.warning(
                "Upload proxy: None - posting from VPS datacenter IP, "
                "0-view shadowban risk (set proxy.endpoint to a Malaysian "
                "residential/4G proxy)")
            self.proxy_url = None

        self.strict_mode = env_flag("TIKTOK_PROXY_STRICT",
                                    default=bool(get_config().get("proxy", "strict_mode", default=True)))
        self.geo_check = env_flag("TIKTOK_PROXY_GEO_CHECK",
                                  default=bool(get_config().get("proxy", "geo_check", default=True)))

    def check_cookie_expiry(self) -> None:
        """Check if TikTok session cookies are fresh enough."""
        user = get_config().get("tiktok", "session_username") or "kumpul.shop"
        uploader_dir = get_config().get("tiktok", "uploader_dir", default="/opt/TiktokAutoUploader")
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
                with open(failed_dir(), "a") as fl:
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
                    with open(failed_dir(), "a", encoding="utf-8") as ff:
                        ff.write(f"{datetime.now().isoformat()} ABORTED proxy "
                                 f"geo check failed: {detail}\n")
                except OSError:
                    pass
                return False
            return True
        logger.warning("Proxy geo check unavailable, continuing unverified "
                       "(set proxy.geo_check=false to skip)")
        return True

    @retry_with_policy(UPLOAD_POLICY)
    def _upload_with_retry(self, session_user: str, video_path: str, title: str,
                           products: List[Dict], proxy: Optional[str]) -> bool:
        """Upload a single video with retry policy."""
        return self.tiktok_adapter.upload_video(
            session_user=session_user,
            video=video_path,
            title=title,
            products=products,
            proxy=proxy
        )

    def process_upload_queue(self) -> UploadResult:
        """Process the next video in the upload queue with idempotency and state tracking."""
        # Acquire upload lock
        lockfile = Path("/tmp/tiktok-machine-upload.lock")
        lockfile.parent.mkdir(parents=True, exist_ok=True)
        with open(lockfile, "w") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                logger.info("Another upload in progress, skipping")
                metrics.increment_counter("jobs_skipped", labels={"reason": "lock_contention"})
                return UploadResult(success=False, error_message="Another upload in progress")

        try:
            cands = self.sidecars.find()
            if not cands:
                logger.info("No video+sidecar found - ensure video_processor ran")
                metrics.increment_counter("jobs_skipped", labels={"reason": "no_candidates"})
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
            logger.info("Session User     : %s", OWN_HANDLE)

            if not self.verify_proxy():
                metrics.increment_counter("jobs_failed", labels={"reason": "proxy_verification_failed"})
                return UploadResult(success=False, error_message="Proxy verification failed")

            # Idempotency: compute video hash
            video_hash = md5_file(mp4)
            existing = self.upload_repo.find_by_video_hash(video_hash)
            if existing and existing.status == UploadJobStatus.SUCCESS:
                logger.info("Video %s already uploaded successfully (job %s), skipping", mp4.name, existing.id)
                metrics.increment_counter("duplicate_prevented", labels={"product": sidecar.get("product_folder", "")})
                self._cleanup_success(mp4, sidecar, sidecar.get("product_id", ""), sidecar.get("title", ""))
                return UploadResult(success=True, error_message="Duplicate skipped")

            # Create or retrieve job record
            job = self.upload_repo.find_by_video_hash(video_hash)
            if not job:
                job = UploadJob(
                    product_name=sidecar.get("product_folder", ""),
                    product_id=sidecar.get("product_id", ""),
                    raw_video_path=str(mp4),
                    processed_video_path="",
                    caption_text=sidecar.get("caption", ""),
                    video_hash=video_hash,
                    source_path=str(mp4),
                    job_uuid=f"job_{int(time.time())}_{random.randint(1000,9999)}",
                    status=UploadJobStatus.DISCOVERED,
                )
                job_id = self.upload_repo.create(job)
                job.id = job_id
            else:
                job_id = job.id

            # State transitions with audit
            self._transition_job(job, UploadJobStatus.QUEUED, "Queued for processing")
            self._transition_job(job, UploadJobStatus.PROCESSING, "Processing started")

            if not self.verify_proxy():
                self._transition_job(job, UploadJobStatus.FAILED, "Proxy verification failed")
                metrics.increment_counter("jobs_failed", labels={"reason": "proxy_verification_failed"})
                return UploadResult(success=False, error_message="Proxy verification failed")

            # Anti-bot jitter
            delay = random.randint(5, 90)
            logger.info("Anti-bot jitter sleeping %ss before upload...", delay)
            time.sleep(delay)

            session_user = OWN_HANDLE
            products = [{"product_id": product_id, "caption": safe_caption}] if product_id else []

            # Upload with retry policy
            try:
                self._transition_job(job, UploadJobStatus.UPLOADING, "Upload attempt")
                success = self._upload_with_retry(
                    session_user=OWN_HANDLE,
                    video_path=str(mp4),
                    title=title,
                    products=products,
                    proxy=self.proxy_url
                )
            except Exception as e:
                logger.exception("Upload failed after retries: %s", e)
                self._handle_upload_failure(job, e)
                return UploadResult(success=False, error_message=str(e))

            if success:
                self._transition_job(job, UploadJobStatus.SUCCESS, "Upload succeeded")
                metrics.increment_counter("jobs_completed", labels={"product": sidecar.get("product_folder", "")})
                self._log_analytics(sidecar)
                self._cleanup_success(mp4, sidecar, product_id, title)
                return UploadResult(
                    success=True,
                    video_path=str(mp4),
                    product_name=sidecar.get("product_folder", ""),
                    product_id=product_id,
                    tiktok_post_id=None,
                )
            else:
                self._transition_job(job, UploadJobStatus.FAILED, "Upload returned False")
                metrics.increment_counter("jobs_failed", labels={"reason": "api_false"})
                return UploadResult(success=False, error_message="Upload returned False")

        except Exception as e:
            logger.exception("Upload service error: %s", e)
            metrics.increment_counter("jobs_failed", labels={"reason": "unexpected_error"})
            return UploadResult(success=False, error_message=str(e))

    def _transition_job(self, job: UploadJob, new_status: UploadJobStatus, reason: str = "") -> None:
        """Transition job state with audit logging."""
        old_status = job.status
        job.status = new_status
        job.updated_at = datetime.utcnow()
        self.upload_repo.update_status_with_audit(job.id, new_status, old_status, reason, "upload_service")
        logger.info("Job %s transition %s -> %s: %s", job.id, old_status.value, new_status.value, reason)

    def _handle_upload_failure(self, job: UploadJob, error: Exception) -> None:
        """Handle upload failure with retry logic."""
        job.retry_count += 1
        job.last_error = str(error)
        job.updated_at = datetime.utcnow()

        if job.retry_count >= job.max_retries or isinstance(error, FatalError):
            self._transition_job(job, UploadJobStatus.DEAD_LETTER, f"Max retries or fatal error: {error}")
            self.upload_repo.set_dead_letter(job.id, str(error))
            metrics.increment_counter("jobs_failed", labels={"reason": "dead_letter"})
        else:
            self._transition_job(job, UploadJobStatus.RETRY_PENDING, f"Retry {job.retry_count}/{job.max_retries}: {error}")
            self.upload_repo.increment_retry_count(job.id, str(error))
            metrics.increment_counter("retries", labels={"operation": "upload", "reason": type(error).__name__})
        """Log upload to analytics database."""
        try:
            from services.repositories import Database
            from services.utils.db_utils import ensure_schema
            conn = Database(db_path())
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
            with open(success_log(), "a", encoding="utf-8") as sf:
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
        failed_dir().mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_dir = failed_dir() / f"{mp4.stem}_{ts}"
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