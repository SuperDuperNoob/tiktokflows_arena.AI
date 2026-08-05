"""Upload job domain model."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class UploadJobStatus(Enum):
    """Status of an upload job."""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    UPLOADING = "UPLOADING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRY = "RETRY"


@dataclass
class UploadJob:
    """Represents an upload job in the pipeline."""
    id: Optional[int] = None
    product_name: str = ""
    product_id: str = ""
    raw_video_path: str = ""
    processed_video_path: str = ""
    caption_text: str = ""
    description_text: Optional[str] = None
    product_tag_text: Optional[str] = None
    sound_file: Optional[str] = None
    speed_factor: Optional[float] = None
    brightness_shift: Optional[float] = None
    status: UploadJobStatus = UploadJobStatus.PENDING
    posted_at: Optional[datetime] = None
    tiktok_post_id: Optional[str] = None
    views: int = 0
    likes: int = 0
    comments: int = 0
    last_analytics_check: Optional[datetime] = None
    proxy_ip_used: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """Convert to dictionary for database storage."""
        return {
            "id": self.id,
            "product_name": self.product_name,
            "product_id": self.product_id,
            "raw_video_path": self.raw_video_path,
            "processed_video_path": self.processed_video_path,
            "caption_text": self.caption_text,
            "description_text": self.description_text,
            "product_tag_text": self.product_tag_text,
            "sound_file": self.sound_file,
            "speed_factor": self.speed_factor,
            "brightness_shift": self.brightness_shift,
            "status": self.status.value,
            "posted_at": self.posted_at.isoformat() if self.posted_at else None,
            "tiktok_post_id": self.tiktok_post_id,
            "views": self.views,
            "likes": self.likes,
            "comments": self.comments,
            "last_analytics_check": self.last_analytics_check.isoformat() if self.last_analytics_check else None,
            "proxy_ip_used": self.proxy_ip_used,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UploadJob":
        """Create UploadJob from database row."""
        status = data.get("status", "PENDING")
        if isinstance(status, str):
            status = UploadJobStatus(status)
        
        return cls(
            id=data.get("id"),
            product_name=data.get("product_name", ""),
            product_id=data.get("product_id", ""),
            raw_video_path=data.get("raw_video_path", ""),
            processed_video_path=data.get("processed_video_path", ""),
            caption_text=data.get("caption_text", ""),
            description_text=data.get("description_text"),
            product_tag_text=data.get("product_tag_text"),
            sound_file=data.get("sound_file"),
            speed_factor=data.get("speed_factor"),
            brightness_shift=data.get("brightness_shift"),
            status=status,
            posted_at=datetime.fromisoformat(data["posted_at"]) if data.get("posted_at") else None,
            tiktok_post_id=data.get("tiktok_post_id"),
            views=data.get("views", 0),
            likes=data.get("likes", 0),
            comments=data.get("comments", 0),
            last_analytics_check=datetime.fromisoformat(data["last_analytics_check"]) if data.get("last_analytics_check") else None,
            proxy_ip_used=data.get("proxy_ip_used"),
            notes=data.get("notes"),
        )