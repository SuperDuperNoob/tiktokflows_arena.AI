"""Proxy adapter for proxy management and verification."""

from typing import Any, Dict, List, Optional
import requests
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts"))
from config import get_config


class ProxyAdapter:
    """Adapter for proxy management and verification."""

    def __init__(self):
        self.config = get_config()

    def normalize_proxy_url(self, raw: str) -> str:
        """Normalize proxy URL to standard format."""
        if not raw:
            return ""
        s = raw.strip().strip('"').strip("'").strip()
        if not s:
            return ""
        if "://" in s:
            return s
        if "@" in s and ":" in s:
            return f"http://{s}"
        
        from urllib.parse import quote as _quote
        
        def _host_like(field: str) -> bool:
            return ("." in field) or field.replace(".", "").isdigit()
        
        parts = s.split(":")
        if len(parts) == 4:
            a_like = _host_like(parts[2]) and parts[3].isdigit()
            b_like = _host_like(parts[0]) and parts[1].isdigit()
            if b_like and not a_like:
                host, port, user, pwd = parts[0], parts[1], parts[2], parts[3]
            elif a_like and not b_like:
                user, pwd, host, port = parts[0], parts[1], parts[2], parts[3]
            elif parts[1].isdigit() and not parts[3].isdigit():
                host, port, user, pwd = parts[0], parts[1], parts[2], parts[3]
            else:
                user, pwd, host, port = parts[0], parts[1], parts[2], parts[3]
            return f"http://{_quote(user, safe='')}:{_quote(pwd, safe='')}@{host}:{port}"
        if len(parts) == 2 and parts[1].isdigit():
            return f"http://{parts[0]}:{parts[1]}"
        return f"http://{s}"

    def mask_proxy(self, url: str) -> Optional[str]:
        """Mask proxy URL for logging."""
        if not url:
            return None
        try:
            norm = self.normalize_proxy_url(url)
            from urllib.parse import urlparse
            p = urlparse(norm if "://" in norm else f"http://{norm}")
            user = ""
            try:
                if p.username:
                    u = p.username
                    user = f"{u[:3]}***@" if len(u) > 3 else "***@"
            except Exception:
                user = "***@"
            try:
                host = p.hostname or "?"
            except Exception:
                host = "?"
            try:
                port = f":{p.port}" if p.port else ""
            except (ValueError, Exception):
                port = ":?"
            except Exception:
                port = ""
            scheme = p.scheme or "http"
            return f"{scheme}://{user}{host}{port}"
        except Exception:
            return "(could not parse TIKTOK_PROXY URL)"

    def check_proxy_exit(self, proxy_url: str, timeout: int = 10) -> tuple[Optional[bool], str]:
        """Verify proxy exits in Malaysia on residential/mobile line."""
        proxies = {"http": proxy_url, "https": proxy_url}
        last_err = "no geo endpoint tried"
        try:
            r = requests.get(
                "http://ip-api.com/json/?fields=status,message,country,countryCode,city,isp,org,mobile,proxy,hosting,query",
                proxies=proxies, timeout=timeout)
            j = r.json()
            if j.get("status") == "success":
                cc = j.get("countryCode", "?")
                kinds = []
                if j.get("mobile"):
                    kinds.append("mobile/4G")
                if j.get("hosting"):
                    kinds.append("DATACENTER-hosting")
                if j.get("proxy"):
                    kinds.append("proxy-flagged")
                if not kinds:
                    kinds.append("residential/ISP")
                detail = (f"exit_ip={j.get('query')} geo={j.get('city', '?')},{cc} "
                          f"isp={j.get('isp', '?')} org={j.get('org', '?')} "
                          f"type={'+'.join(kinds)}")
                ok = (cc == "MY") and not j.get("hosting")
                return ok, detail
            last_err = f"ip-api: {j.get('message', 'unknown error')}"
        except Exception as e:
            last_err = f"ip-api: {e}"
        try:
            r = requests.get("https://ipinfo.io/json", proxies=proxies, timeout=timeout)
            j = r.json()
            if j.get("ip"):
                cc = j.get("country", "?")
                detail = (f"exit_ip={j.get('ip')} geo={j.get('city', '?')},{cc} "
                          f"org={j.get('org', '?')} type=unknown(ip-api fallback)")
                return (cc == "MY"), detail
            last_err = f"{last_err}; ipinfo: no ip in response"
        except Exception as e:
            last_err = f"{last_err}; ipinfo: {e}"
        return None, f"geo check failed: {last_err}"

    def is_proxy_transport_error(self, exc: Exception) -> bool:
        """Check if exception is a proxy transport error."""
        try:
            import requests
            if isinstance(exc, (requests.exceptions.ProxyError,
                                requests.exceptions.ConnectTimeout)):
                return True
        except Exception:
            pass
        msg = str(exc).lower()
        return any(s in msg for s in (
            "proxyerror",
            "cannot connect to proxy",
            "unable to connect to proxy",
            "tunnel connection failed",
            "407 proxy authentication required",
        ))

    def verify(self, proxy_url: Optional[str] = None) -> Dict[str, Any]:
        """Verify a proxy and return status."""
        from services.models import ProxyStatus, ProxyType
        
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
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts"))
        from config import get_config
        
        cfg = get_config()
        raw_proxy = cfg.get("proxy", "endpoint", default="") or ""
        raw_proxy = os.environ.get("TIKTOK_PROXY", raw_proxy).strip()
        if raw_proxy:
            return self.normalize_proxy_url(raw_proxy)
        return None