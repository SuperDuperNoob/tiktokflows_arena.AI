"""Proxy service for proxy management and verification."""

from typing import Any, Dict, List, Optional

from services.infrastructure.proxy_adapter import ProxyAdapter
from services.models import ProxyStatus


class ProxyService:
    """Service for proxy management."""

    def __init__(self):
        self.proxy_adapter = ProxyAdapter()

    def get_current_proxy(self) -> Optional[str]:
        """Get the current proxy URL from config."""
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
        from config import get_config
        
        cfg = get_config()
        return cfg.get("proxy", "endpoint")

    def verify_proxy(self, proxy_url: Optional[str] = None) -> ProxyStatus:
        """Verify a proxy's exit IP and type."""
        from services.infrastructure.proxy_adapter import ProxyAdapter
        
        adapter = ProxyAdapter()
        return adapter.verify(proxy_url)

    def get_proxy_status(self) -> Dict[str, Any]:
        """Get current proxy status."""
        proxy_url = self.get_current_proxy()
        if not proxy_url:
            return {"configured": False, "error": "No proxy configured"}
        
        status = self.verify_proxy(proxy_url)
        return {
            "configured": True,
            "url": proxy_url,
            "status": status.to_dict(),
        }

    def check_proxy_health(self) -> bool:
        """Quick health check for proxy."""
        proxy_url = self.get_current_proxy()
        if not proxy_url:
            return False
        
        status = self.verify_proxy(proxy_url)
        return status.is_valid