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
            "tiktok_post_id": job.tiktok_video_id,
            "views": job.views,
            "likes": job.likes,
            "comments": job.comments,
            "last_analytics_check": job.last_analytics_check.isoformat() if job.last_analytics_check else None,
            "proxy_ip_used": job.proxy_ip_used,
            "notes": job.notes,
            "video_hash": job.video_hash,
            "source_path": job.source_path,
            "job_uuid": job.job_uuid,
            "compliance_status": job.compliance_status,
            "compliance_details": job.compliance_details,
            "retry_count": job.retry_count,
            "max_retries": job.max_retries,
            "last_error": job.last_error,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
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
            "updated_at": datetime.utcnow().isoformat(),
        }
        if proxy_ip:
            data["proxy_ip_used"] = proxy_ip
        if tiktok_post_id:
            data["tiktok_post_id"] = tiktok_post_id
        if notes:
            data["notes"] = notes

        return self.update("posts", data, "id = ?", (job_id,))

    def update_status_with_audit(self, job_id: int, new_status: UploadJobStatus,
                                 old_status: UploadJobStatus,
                                 reason: str = "", component: str = "") -> int:
        """Update status and log audit trail."""
        # In a real implementation, write to audit_log table.
        # For now, just update status and log via logger.
        from services.infrastructure.logging import get_logger
        logger = get_logger("audit")
        logger.info("Status transition",
                    extra={"job_id": job_id,
                           "old_status": old_status.value,
                           "new_status": new_status.value,
                           "reason": reason,
                           "component": component})
        return self.update_status(job_id, new_status)

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
        """Get the most recent post time, optionally filtered by product."""
        if product_name:
            row = self.fetchone(
                "SELECT posted_at FROM posts WHERE product_name = ? AND status = ? ORDER BY posted_at DESC LIMIT 1",
                (product_name, "SUCCESS"),
            )
        else:
            row = self.fetchone(
                "SELECT posted_at FROM posts WHERE status = ? ORDER BY posted_at DESC LIMIT 1",
                ("SUCCESS",),
            )
        if row and row["posted_at"]:
            return datetime.fromisoformat(row["posted_at"])
        return None

    # New methods for workflow reliability
    def find_by_status(self, status: UploadJobStatus, limit: int = 100) -> List[UploadJob]:
        """Find jobs by status."""
        rows = self.fetchall(
            "SELECT * FROM posts WHERE status = ? ORDER BY created_at ASC LIMIT ?",
            (status.value, limit),
        )
        return [UploadJob.from_dict(row) for row in rows]

    def find_by_video_hash(self, video_hash: str) -> Optional[UploadJob]:
        """Find job by video hash for idempotency."""
        row = self.fetchone(
            "SELECT * FROM posts WHERE video_hash = ? ORDER BY created_at DESC LIMIT 1",
            (video_hash,),
        )
        return UploadJob.from_dict(row) if row else None

    def find_by_job_uuid(self, job_uuid: str) -> Optional[UploadJob]:
        """Find job by UUID."""
        row = self.fetchone(
            "SELECT * FROM posts WHERE job_uuid = ? ORDER BY created_at DESC LIMIT 1",
            (job_uuid,),
        )
        return UploadJob.from_dict(row) if row else None

    def find_unfinished_jobs(self) -> List[UploadJob]:
        """Find jobs that are not in a terminal state."""
        terminal_statuses = ("SUCCESS", "FAILED", "ABANDONED", "DEAD_LETTER")
        placeholders = ",".join("?" * len(terminal_statuses))
        rows = self.fetchall(
            f"SELECT * FROM posts WHERE status NOT IN ({placeholders}) ORDER BY created_at ASC",
            terminal_statuses,
        )
        return [UploadJob.from_dict(row) for row in rows]

    def find_retry_pending_jobs(self, limit: int = 50) -> List[UploadJob]:
        """Find jobs that are pending retry."""
        rows = self.fetchall(
            "SELECT * FROM posts WHERE status = ? AND retry_count < max_retries ORDER BY updated_at ASC LIMIT ?",
            (UploadJobStatus.RETRY_PENDING.value, limit),
        )
        return [UploadJob.from_dict(row) for row in rows]

    def increment_retry_count(self, job_id: int, error_message: str) -> int:
        """Increment retry count and store error."""
        return self.execute(
            "UPDATE posts SET retry_count = retry_count + 1, last_error = ?, updated_at = ? WHERE id = ?",
            (error_message, datetime.utcnow().isoformat(), job_id)
        ).rowcount

    def set_dead_letter(self, job_id: int, reason: str) -> int:
        """Mark job as dead letter."""
        return self.update("posts",
                           {"status": "DEAD_LETTER",
                            "last_error": reason,
                            "updated_at": datetime.utcnow().isoformat()},
                           "id = ?", (job_id,))

    def mark_compliance(self, job_id: int, passed: bool, details: str = "") -> int:
        """Record compliance check result."""
        status = "COMPLIANCE_PASSED" if passed else "COMPLIANCE_FAILED"
        return self.update("posts",
                           {"status": status,
                            "compliance_status": status,
                            "compliance_details": details,
                            "updated_at": datetime.utcnow().isoformat()},
                           "id = ?", (job_id,))

    def update_retry_schedule(self, job_id: int, next_retry_at: datetime) -> int:
        """Schedule next retry."""
        return self.update("posts",
                           {"status": "RETRY_PENDING",
                            "updated_at": datetime.utcnow().isoformat()},
                           "id = ?", (job_id,))