"""Upload repository for managing upload jobs."""

from typing import Any, Dict, List, Optional
from datetime import datetime

from .base import BaseRepository
from services.models.upload_job import UploadJob, UploadJobStatus


class UploadRepository(BaseRepository):
    """Repository for upload job operations."""

    def __init__(self, db_path: str):
        super().__init__(db_path)

    def get_table_name(self) -> str:
        return "posts"

    def create(self, job: UploadJob) -> int:
        """Create a new upload job."""
        data = {
            "product_name": job.product_name,
            "product_id": job.product_id,
            "raw_video_path": job.raw_video_path,
            "processed_video_path": job.processed_video_path,
            "caption_text": job.caption_text,
            "description_text": job.description_text,
            "product_tag_text": job.product_tag_text,
            "sound_file": job.sound_file,
            "speed_factor": job.speed_factor,
            "brightness_shift": job.brightness_shift,
            "status": job.status.value,
            "posted_at": job.posted_at.isoformat() if job.posted_at else None,
            "tiktok_post_id": job.tiktok_post_id,
            "views": job.views,
            "likes": job.likes,
            "comments": job.comments,
            "proxy_ip_used": job.proxy_ip_used,
            "notes": job.notes,
        }
        return self.insert("posts", data)

    def update_status(self, job_id: int, status: UploadJobStatus, 
                      proxy_ip: Optional[str] = None,
                      tiktok_post_id: Optional[str] = None,
                      notes: Optional[str] = None) -> int:
        """Update upload job status."""
        data = {
            "status": status.value,
            "posted_at": datetime.utcnow().isoformat(),
        }
        if proxy_ip:
            data["proxy_ip_used"] = proxy_ip
        if tiktok_post_id:
            data["tiktok_post_id"] = tiktok_post_id
        if notes:
            data["notes"] = notes
        
        return self.update("posts", data, "id = ?", (job_id,))

    def get_by_id(self, job_id: int) -> Optional[UploadJob]:
        """Get upload job by ID."""
        row = self.fetchone("SELECT * FROM posts WHERE id = ?", (job_id,))
        return UploadJob.from_dict(row) if row else None

    def get_recent(self, limit: int = 50) -> List[UploadJob]:
        """Get recent upload jobs."""
        rows = self.fetchall(
            "SELECT * FROM posts ORDER BY posted_at DESC LIMIT ?", (limit,)
        )
        return [UploadJob.from_dict(row) for row in rows]

    def get_by_product(self, product_name: str, limit: int = 50) -> List[UploadJob]:
        """Get upload jobs by product."""
        rows = self.fetchall(
            "SELECT * FROM posts WHERE product_name = ? ORDER BY posted_at DESC LIMIT ?",
            (product_name, limit),
        )
        return [UploadJob.from_dict(row) for row in rows]

    def get_today_count(self) -> int:
        """Get count of posts today."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        row = self.fetchone(
            "SELECT COUNT(*) as cnt FROM posts WHERE date(posted_at) = ? AND status = ?",
            (today, "POSTED"),
        )
        return row["cnt"] if row else 0

    def get_last_post_time(self, product_name: Optional[str] = None) -> Optional[datetime]:
        """Get last post time."""
        if product_name:
            row = self.fetchone(
                "SELECT posted_at FROM posts WHERE product_name = ? AND status = ? ORDER BY posted_at DESC LIMIT 1",
                (product_name, "POSTED"),
            )
        else:
            row = self.fetchone(
                "SELECT posted_at FROM posts WHERE status = ? ORDER BY posted_at DESC LIMIT 1",
                ("POSTED",),
            )
        if row and row["posted_at"]:
            return datetime.fromisoformat(row["posted_at"])
        return None