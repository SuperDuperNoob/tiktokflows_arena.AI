"""Video processing service."""

from typing import Any, Dict, List, Optional
from pathlib import Path

from services.repositories import StockRepository
from services.models import VideoAsset, VideoQuality
from services.infrastructure.ffmpeg_adapter import FFmpegAdapter
from services.infrastructure.skia_adapter import SkiaAdapter


class VideoService:
    """Service for video processing and transformation."""

    def __init__(self):
        self.stock_repo = StockRepository()
        self.ffmpeg = FFmpegAdapter()
        self.skia = SkiaAdapter()

    def process_video(self, raw_video_path: Path, product_name: str,
                      caption: str, audio_mode: str = "mix") -> Dict[str, Any]:
        """Process a raw video: transform, add overlay, add audio."""
        # This would integrate with the FFmpeg and Skia adapters
        return {
            "processed_path": "",
            "transform_params": {},
        }

    def select_video(self, product_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Select the next video to process."""
        return None

    def validate_video(self, video_path: Path) -> VideoQuality:
        """Validate video quality."""
        return VideoQuality.UNKNOWN