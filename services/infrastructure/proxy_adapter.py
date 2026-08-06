"""Proxy adapter for proxy management and verification."""

from typing import Any, Dict, List, Optional
import os
import requests
from scripts.config import get_config
from services.utils.proxy import (
    normalize_proxy_url,
    mask_proxy,
    check_proxy_exit,
    is_proxy_transport_error,
)
from services.models import ProxyStatus, ProxyType


class ProxyAdapter:
    """Adapter for proxy management and verification."""

    def __init__(self):
        self.config = get_config()

    def normalize_proxy_url(self, raw: str) -> str:
        """Normalize proxy URL to standard format."""
        return normalize_proxy_url(raw)

    def mask_proxy(self, url: str) -> Optional[str]:
        """Mask proxy URL for logging."""
        return mask_proxy(url)

    def check_proxy_exit(self, proxy_url: str, timeout: int = 10) -> tuple[Optional[bool], str]:
        """Verify proxy exits in Malaysia on residential/mobile line."""
        return check_proxy_exit(proxy_url, timeout)

    def is_proxy_transport_error(self, exc: Exception) -> bool:
        """Check if exception is a proxy transport error."""
        return is_proxy_transport_error(exc)

    def verify(self, proxy_url: Optional[str] = None) -> Dict[str, Any]:
        """Verify a proxy and return status."""

        if not proxy_url:
            proxy_url = self.get_current_proxy()

        if not proxy_url:
            return ProxyStatus(
                is_valid=False,
                proxy_url="",
                error="No proxy configured",
            ).to_dict()

        normalized = self.normalize_proxy_url(proxy_url)
        ok, detail = self.check_proxy_exit(normalized)

        status = ProxyStatus(
            proxy_url=normalized,
            is_valid=ok is True,
            detail=detail,
        )

        if ok is True:
            status.proxy_type = ProxyType.RESIDENTIAL
        elif ok is False:
            status.proxy_type = ProxyType.DATACENTER

        return status.to_dict()

    def get_current_proxy(self) -> Optional[str]:
        """Get current proxy from config."""
        cfg = get_config()
        raw_proxy = cfg.get("proxy", "endpoint", default="") or ""
        raw_proxy = os.environ.get("TIKTOK_PROXY", raw_proxy).strip()
        if raw_proxy:
            return self.normalize_proxy_url(raw_proxy)
        return None