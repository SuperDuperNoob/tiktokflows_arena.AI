"""Upload Service CLI - thin wrapper for services.core.UploadService"""

import argparse
import logging
import sys
import os

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, SCRIPTS_DIR)

from services.core.upload_service import UploadService
from services.infrastructure.config import get_config
from services.utils.proxy import check_proxy_exit, normalize_proxy_url, is_proxy_transport_error, mask_proxy

logger = logging.getLogger(__name__)


def env_flag(name: str, default: bool = False) -> bool:
    """Read environment variable as boolean flag."""
    val = os.environ.get(name, "").strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default


class Uploader:
    """Legacy wrapper for backward compatibility."""

    def __init__(self, config: dict | None = None, dry_run: bool = False):
        self.config = config if config is not None else get_config()._data
        self.dry_run = dry_run
        self.service = UploadService()

        # Expose attributes for backward compatibility with tests
        raw_proxy = get_config().get("proxy", "endpoint", default="") or ""
        raw_proxy = os.environ.get("TIKTOK_PROXY", raw_proxy).strip()
        self.proxy_url = normalize_proxy_url(raw_proxy) if raw_proxy else None
        
        self.strict_mode = env_flag("TIKTOK_PROXY_STRICT",
                                    default=bool(get_config().get("proxy", "strict_mode", default=True)))
        self.geo_check = env_flag("TIKTOK_PROXY_GEO_CHECK",
                                  default=bool(get_config().get("proxy", "geo_check", default=True)))

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
                return False
            return True
        logger.warning("Proxy geo check unavailable, continuing unverified "
                       "(set proxy.geo_check=false to skip)")
        return True

    def upload(self) -> int:
        result = self.service.process_upload_queue()
        if result.success:
            logger.info("Upload successful")
            return 0
        else:
            logger.error("Upload failed: %s", result.error_message)
            return 1


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser(description="TikTok Auto Uploader")
    ap.add_argument("--dry-run", action="store_true", help="Skip actual upload")
    args = ap.parse_args()

    uploader = Uploader(dry_run=args.dry_run)
    return uploader.upload()


if __name__ == "__main__":
    sys.exit(main())