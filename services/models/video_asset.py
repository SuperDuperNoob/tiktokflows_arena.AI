"""Video asset domain model."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any


class VideoQuality(Enum):
    """Quality assessment of a video."""
    UNKNOWN = "UNKNOWN"
    GOOD = "GOOD"
    LOW_BITRATE = "LOW_BITRATE"
    STATIC_IMAGE = "STATIC_IMAGE"
    CORRUPT = "CORRUPT"


@dataclass
class VideoAsset:
    """Represents a video asset in the pipeline."""
    id: Optional[str] = None
    product_name: str = ""
    file_path: Path = field(default_factory=Path)
    file_size: int = 0
    duration: float = 0.0
    frame_count: int = 0
    width: int = 0
    height: int = 0
    bitrate: int = 0
    mb_per_sec: float = 0.0
    quality: VideoQuality = VideoQuality.UNKNOWN
    quality_issues: list = field(default_factory=list)
    encoding_params: Dict[str, Any] = field(default_factory=dict)
    sidecar_path: Optional[Path] = None
    processed_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_ready_for_upload(self) -> bool:
        """Check if video is ready for upload."""
        return (
            self.quality == VideoQuality.GOOD
            and self.file_path.exists()
            and self.sidecar_path is not None
            and self.sidecar_path.exists()
        )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "product_name": self.product_name,
            "file_path": str(self.file_path),
            "file_size": self.file_size,
            "duration": self.duration,
            "frame_count": self.frame_count,
            "width": self.width,
            "height": self.height,
            "bitrate": self.bitrate,
            "mb_per_sec": self.mb_per_sec,
            "quality": self.quality.value,
            "quality_issues": self.quality_issues,
            "encoding_params": self.encoding_params,
            "sidecar_path": str(self.sidecar_path) if self.sidecar_path else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "archived_at": self.archived_at.isoformat() if self.archived_at else None,
            "metadata": self.metadata,
        }