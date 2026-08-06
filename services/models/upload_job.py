"""Upload job domain model."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class UploadJobStatus(Enum):
    """Status of an upload job."""
    DISCOVERED = "DISCOVERED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLIANCE_PASSED = "COMPLIANCE_PASSED"
    COMPLIANCE_FAILED = "COMPLIANCE_FAILED"
    UPLOADING = "UPLOADING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RETRY_PENDING = "RETRY_PENDING"
    ABANDONED = "ABANDONED"
    DEAD_LETTER = "DEAD_LETTER"


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
    status: UploadJobStatus = UploadJobStatus.DISCOVERED
    posted_at: Optional[datetime] = None
    tiktok_video_id: Optional[str] = None
    views: int = 0
    likes: int = 0
    comments: int = 0
    last_analytics_check: Optional[datetime] = None
    proxy_ip_used: Optional[str] = None
    notes: Optional[str] = None
    # Idempotency fields
    video_hash: Optional[str] = None
    source_path: Optional[str] = None
    job_uuid: Optional[str] = None
    # Compliance
    compliance_status: Optional[str] = None
    compliance_details: Optional[str] = None
    # Retry
    retry_count: int = 0
    max_retries: int = 3
    last_error: Optional[str] = None
    # Timestamps
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
            "tiktok_video_id": self.tiktok_video_id,
            "views": self.views,
            "likes": self.likes,
            "comments": self.comments,
            "last_analytics_check": self.last_analytics_check.isoformat() if self.last_analytics_check else None,
            "proxy_ip_used": self.proxy_ip_used,
            "notes": self.notes,
            "video_hash": self.video_hash,
            "source_path": self.source_path,
            "job_uuid": self.job_uuid,
            "compliance_status": self.compliance_status,
            "compliance_details": self.compliance_details,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "last_error": self.last_error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UploadJob":
        """Create UploadJob from database row."""
        status = data.get("status", "DISCOVERED")
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
            tiktok_video_id=data.get("tiktok_video_id"),
            views=data.get("views", 0),
            likes=data.get("likes", 0),
            comments=data.get("comments", 0),
            last_analytics_check=datetime.fromisoformat(data["last_analytics_check"]) if data.get("last_analytics_check") else None,
            proxy_ip_used=data.get("proxy_ip_used"),
            notes=data.get("notes"),
            video_hash=data.get("video_hash"),
            source_path=data.get("source_path"),
            job_uuid=data.get("job_uuid"),
            compliance_status=data.get("compliance_status"),
            compliance_details=data.get("compliance_details"),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            last_error=data.get("last_error"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
        )