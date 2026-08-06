"""Scheduler service for managing the posting schedule."""

from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone
import random

from services.repositories import UploadRepository
from services.utils.timezone import MYT_OFFSET, MYT


class SchedulerService:
    """Service for scheduling and timing management."""

    def __init__(self, db_path: str):
        self.upload_repo = UploadRepository(db_path)

    def should_post_now(self, config: Dict[str, Any]) -> bool:
        """Determine if it's time to post."""
        # MYT timezone (UTC+8)
        now = datetime.now(MYT)
        posting = config.get("posting", {})

        # Check quiet hours
        hour = now.hour
        qs = posting.get("quiet_hours_start", 2)
        qe = posting.get("quiet_hours_end", 6)
        if qs <= hour < qe:
            return False

        last_post = self.upload_repo.get_last_post_time()
        if last_post is None:
            return True

        base = posting.get("interval_minutes", 120)
        jitter = random.uniform(-posting.get("jitter_minutes", 30),
                                posting.get("jitter_minutes", 30))
        required = (base + jitter) * 60
        elapsed = (datetime.now(timezone.utc) - last_post).total_seconds()
        return elapsed >= required

    def get_next_post_time(self, config: Dict[str, Any]) -> Optional[datetime]:
        """Get the next scheduled post time."""
        last_post = self.upload_repo.get_last_post_time()
        if last_post is None:
            return datetime.now(timezone.utc)

        posting = config.get("posting", {})
        base = posting.get("interval_minutes", 120)
        jitter = random.uniform(-posting.get("jitter_minutes", 30),
                                posting.get("jitter_minutes", 30))
        required = (base + jitter) * 60

        next_time = last_post + timedelta(seconds=required)
        return next_time

    def is_quiet_hours(self, config: Dict[str, Any]) -> bool:
        """Check if currently in quiet hours."""
        now = datetime.now(MYT)
        posting = config.get("posting", {})
        hour = now.hour
        qs = posting.get("quiet_hours_start", 2)
        qe = posting.get("quiet_hours_end", 6)
        return qs <= hour < qe