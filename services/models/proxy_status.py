"""Proxy status domain model."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class ProxyType(Enum):
    """Type of proxy."""
    RESIDENTIAL = "residential"
    MOBILE = "mobile"
    DATACENTER = "datacenter"
    UNKNOWN = "unknown"


@dataclass
class ProxyStatus:
    """Result of a proxy verification check."""
    is_valid: bool = False
    proxy_url: str = ""
    exit_ip: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    org: Optional[str] = None
    proxy_type: ProxyType = ProxyType.UNKNOWN
    is_hosting: bool = False
    is_mobile: bool = False
    is_proxy: bool = False
    detail: str = ""
    checked_at: datetime = field(default_factory=lambda: datetime.utcnow())
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "is_valid": self.is_valid,
            "proxy_url": self.proxy_url,
            "exit_ip": self.exit_ip,
            "country": self.country,
            "city": self.city,
            "org": self.org,
            "proxy_type": self.proxy_type.value,
            "is_hosting": self.is_hosting,
            "is_mobile": self.is_mobile,
            "is_proxy": self.is_proxy,
            "detail": self.detail,
            "checked_at": self.checked_at.isoformat(),
            "error": self.error,
        }