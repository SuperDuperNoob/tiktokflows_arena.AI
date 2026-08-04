"""
uploader.py - resilient TikTok uploader (port of auto_uploader_v4.py).

Production hardening kept:
  - Proxy shorthand parsing: any vendor format normalised to
    http://user:pass@host:port and logged MASKED (scheme://use***@host:port).
  - Pre-upload exit-IP geo check (~2KB) via ip-api.com + ipinfo.io fallback, so
    a dead/wrong-country proxy never burns a full metered upload.
  - TIKTOK_PROXY_STRICT: abort the run on a verified-bad proxy exit.
  - NO retry on proxy transport errors (protects metered proxy GB).
  - TikTok API failures DO retry with backoff.
  - Sidecar-driven: only posts mp4s that carry a .json/.pid sidecar, and
    cleans them up after a successful upload.
  - Anti-bot jitter, cookie-age check, duplicate-hash warning, single-run
    flock lock, analytics logging.

Run:  python3 uploader.py            (upload one queued video)
      python3 uploader.py --dry-run  (run all checks, skip the actual upload)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import lib
from lib import (check_proxy_exit, env_flag, is_proxy_transport_error,
                 mask_proxy, normalize_proxy_url)
from sidecar_manager import SidecarManager

logger = logging.getLogger("uploader")


def md5_file(p: Path) -> str:
    h = hashlib.md5()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


class Uploader:
    """Uploads one queued video per run, with proxy + retry hardening."""

    def __init__(self, config: dict | None = None, dry_run: bool = False):
        self.config = config if config is not None else lib.config()
        self.dry_run = dry_run
        self.proxy_url: str | None = None
        self.sidecars = SidecarManager(lib.queue_dir())

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

        self.strict_mode = env_flag("TIKTOK_PROXY_STRICT",
                                    default=bool(lib.cfg("proxy", "strict_mode", default=True)))
        self.geo_check = env_flag("TIKTOK_PROXY_GEO_CHECK",
                                  default=bool(lib.cfg("proxy", "geo_check", default=True)))

    # ------------------------------------------------------------- checks ----

    def check_cookie_expiry(self) -> None:
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
                if self.dry_run:
                    logger.info("STRICT: real run WOULD abort here before "
                                "burning proxy GB (dry-run continues)")
                    return True
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

    # ------------------------------------------------------------ upload ----

    def _upload_once(self, session_user: str, video: str, title: str,
                     products: list, proxy) -> bool:
        try:
            from tiktok_uploader.tiktok_v2 import upload_video
        except Exception as e:
            logger.error("Failed to import TiktokAutoUploader: %s", e)
            raise
        return bool(upload_video(session_user=session_user, video=video,
                                 title=title, products=products, proxy=proxy))

    def _log_analytics(self, sidecar: dict) -> None:
        try:
            conn = lib.get_conn()
            lib.ensure_schema(conn)
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

    def upload(self) -> int:
        cands = self.sidecars.find()
        if not cands:
            logger.info("No video+sidecar found - ensure video_processor ran")
            return 1
        # Pick the newest with a sidecar, penalising recent product repeats.
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
            return 1

        if self.dry_run:
            print("--- DRY RUN: would upload above ---")
            return 0

        # Anti-bot jitter.
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
                success = self._upload_once(
                    session_user, str(mp4), title, products, self.proxy_url)
                if success:
                    logger.info("Upload SUCCESS for %s", mp4.name)
                    self._log_analytics(sidecar)
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
                    return 0
                else:
                    logger.error("Upload returned False (TikTok API error) "
                                 "attempt %d", attempt)
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
        try:
            with open(lib.failed_log(), "a", encoding="utf-8") as ff:
                ff.write(f"{datetime.now().isoformat()} FAILED {mp4.name} "
                         f"product={sidecar.get('product_folder')} "
                         f"reason={last_exc} file={mp4}\n")
        except OSError:
            pass
        self._move_to_failed(mp4, last_exc)
        return 1

    def _move_to_failed(self, mp4: Path, reason: str) -> None:
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


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser(description="TikTok Auto Uploader")
    ap.add_argument("--dry-run", action="store_true", help="Skip actual upload")
    args = ap.parse_args()

    import fcntl
    lockfile = Path("/tmp/tiktok-machine-upload.lock")
    lockfile.parent.mkdir(parents=True, exist_ok=True)
    with open(lockfile, "w") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print("[uploader] another upload in progress, exiting 0")
            return 0
        return Uploader(dry_run=args.dry_run).upload()


if __name__ == "__main__":
    sys.exit(main())
