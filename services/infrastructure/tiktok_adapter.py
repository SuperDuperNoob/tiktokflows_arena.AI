"""TikTok adapter for interacting with TikTokAutoUploader."""

from typing import Any, Dict, List, Optional
from pathlib import Path

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts"))
from config import get_config


class TikTokAdapter:
    """Adapter for TikTokAutoUploader."""

    def __init__(self):
        self.config = get_config()

    def upload_video(self, session_user: str, video_path: str, title: str,
                     products: List[Dict[str, Any]], proxy: Optional[str] = None) -> bool:
        """Upload a video using TikTokAutoUploader."""
        try:
            from tiktok_uploader.tiktok_v2 import upload_video
        except ImportError:
            # Fallback to v1 if v2 not available
            from tiktok_uploader import tiktok as tt_uploader
            upload_video = tt_uploader.upload_video
        
        return bool(upload_video(
            session_user=session_user,
            video=video_path,
            title=title,
            schedule_time=0,
            allow_comment=1,
            allow_duet=0,
            allow_stitch=0,
            visibility_type=0,
            brand_organic_type=0,
            branded_content_type=0,
            ai_label=0,
            proxy=proxy,
            products=products if products else None,
        ))

    def login(self, username: str, uploader_dir: Optional[str] = None) -> bool:
        """Perform login."""
        return False

    def check_cookie_age(self, username: str) -> int:
        """Check cookie age in hours."""
        return 0