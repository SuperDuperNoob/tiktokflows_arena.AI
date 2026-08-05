"""Upload result domain model."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any


@dataclass
class UploadResult:
    """Result of an upload attempt."""
    success: bool
    video_path: str = ""
    product_name: str = ""
    product_id: str = ""
    tiktok_post_id: Optional[str] = None
    proxy_ip: Optional[str] = None
    proxy_used: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    uploaded_at: datetime = field(default_factory=lambda: datetime.utcnow())
    file_size: int = 0
    file_hash: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "video_path": self.video_path,
            "product_name": self.product_name,
            "product_id": self.product_id,
            "tiktok_post_id": self.tiktok_post_id,
            "proxy_ip": self.proxy_ip,
            "proxy_used": self.proxy_used,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "uploaded_at": self.uploaded_at.isoformat(),
            "file_size": self.file_size,
            "file_hash": self.file_hash,
            "metadata": self.metadata,
        }