"""Recovery Manager for workflow reliability and crash recovery."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import List, Optional

from services.repositories import UploadRepository
from services.models.upload_job import UploadJob, UploadJobStatus
from services.infrastructure.logging import get_logger
from services.core.metrics_service import metrics
from services.exceptions import FatalError, RetryableError

logger = get_logger("recovery_manager")


class RecoveryManager:
    """Manages workflow recovery, crash recovery, and job reconciliation."""

    def __init__(self, upload_repo: UploadRepository, max_processing_age_hours: int = 2):
        self.upload_repo = upload_repo
        self.max_processing_age = timedelta(hours=max_processing_age_hours)

    def run_startup_reconciliation(self) -> dict:
        """Run startup reconciliation: find unfinished jobs and decide their fate."""
        logger.info("Starting workflow reconciliation...")
        start_time = time.time()

        unfinished = self.upload_repo.find_unfinished_jobs()
        logger.info(f"Found {len(unfinished)} unfinished jobs")

        results = {
            "total_unfinished": len(unfinished),
            "recovered": 0,
            "abandoned": 0,
            "dead_lettered": 0,
            "left_pending": 0,
            "errors": []
        }

        for job in unfinished:
            try:
                action = self._decide_job_fate(job)
                if action == "retry":
                    self._schedule_retry(job)
                    results["recovered"] += 1
                elif action == "abandon":
                    self._abandon_job(job)
                    results["abandoned"] += 1
                elif action == "dead_letter":
                    self._dead_letter_job(job)
                    results["dead_lettered"] += 1
                else:
                    results["left_pending"] += 1

                metrics.increment_counter("recovery_actions", labels={"action": action})

            except Exception as e:
                logger.exception("Error processing job %s during reconciliation", job.id)
                results["errors"].append({"job_id": job.id, "error": str(e)})

        duration = time.time() - start_time
        logger.info(f"Reconciliation completed in {duration:.2f}s: {results}")
        return results

    def _decide_job_fate(self, job: UploadJob) -> str:
        """Decide what to do with an unfinished job based on its state and age."""
        age = datetime.utcnow() - job.updated_at if job.updated_at else timedelta.max

        # Terminal states should not be here, but guard anyway
        if job.status in (UploadJobStatus.SUCCESS, UploadJobStatus.FAILED,
                          UploadJobStatus.ABANDONED, UploadJobStatus.DEAD_LETTER):
            return "ignore"

        # Jobs stuck in PROCESSING or UPLOADING for too long -> abandon
        if job.status in (UploadJobStatus.PROCESSING, UploadJobStatus.UPLOADING):
            if age > self.max_processing_age:
                logger.warning("Job %s stuck in %s for %s, abandoning", job.id, job.status, age)
                return "abandon"
            return "retry"

        # Retry pending with retries left -> retry
        if job.status == UploadJobStatus.RETRY_PENDING:
            if job.retry_count < job.max_retries:
                return "retry"
            else:
                return "dead_letter"

        # Compliance failed -> dead letter
        if job.status == UploadJobStatus.COMPLIANCE_FAILED:
            return "dead_letter"

        # Compliance passed but not uploaded -> retry
        if job.status == UploadJobStatus.COMPLIANCE_PASSED:
            return "retry"

        # Discovered/Queued -> retry
        if job.status in (UploadJobStatus.DISCOVERED, UploadJobStatus.QUEUED):
            return "retry"

        # Unknown -> left pending
        return "ignore"

    def _schedule_retry(self, job: UploadJob) -> None:
        """Schedule a job for retry."""
        self.upload_repo.update_retry_schedule(job.id, datetime.utcnow())
        logger.info("Scheduled retry for job %s (attempt %d/%d)", job.id, job.retry_count, job.max_retries)

    def _abandon_job(self, job: UploadJob) -> None:
        """Mark job as abandoned."""
        self.upload_repo.update_status_with_audit(
            job.id, UploadJobStatus.ABANDONED, job.status,
            reason="Abandoned due to timeout", component="recovery_manager")
        logger.warning("Abandoned job %s (was %s)", job.id, job.status)

    def _dead_letter_job(self, job: UploadJob) -> None:
        """Move job to dead letter queue."""
        reason = job.last_error or "Max retries exceeded or compliance failed"
        self.upload_repo.set_dead_letter(job.id, reason)
        logger.error("Dead-lettered job %s: %s", job.id, reason)

    def detect_abandoned_jobs(self, max_age_hours: int = 24) -> List[UploadJob]:
        """Detect jobs that appear abandoned (stuck in non-terminal state for too long)."""
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        jobs = self.upload_repo.find_unfinished_jobs()
        abandoned = [
            job for job in jobs
            if job.updated_at and job.updated_at < cutoff
        ]
        return abandoned

    def recover_job(self, job_id: int) -> bool:
        """Manually recover a specific job (operator command)."""
        job = self.upload_repo.get_by_id(job_id)
        if not job:
            logger.error("Job %s not found for recovery", job_id)
            return False

        if job.status in (UploadJobStatus.SUCCESS, UploadJobStatus.FAILED,
                          UploadJobStatus.ABANDONED, UploadJobStatus.DEAD_LETTER):
            logger.warning("Job %s is in terminal state %s, cannot recover", job_id, job.status)
            return False

        # Reset to appropriate retry state
        self.upload_repo.update_status_with_audit(
            job.id, UploadJobStatus.RETRY_PENDING, job.status,
            reason="Manual recovery by operator", component="recovery_manager")
        logger.info("Manually recovered job %s", job_id)
        return True

    def get_workflow_summary(self) -> dict:
        """Get summary of current workflow state."""
        all_jobs = self.upload_repo.find_unfinished_jobs()
        summary = {
            "total_unfinished": len(all_jobs),
            "by_status": {},
            "oldest_job_age_hours": 0,
            "retry_pending": 0,
        }

        if all_jobs:
            ages = [(datetime.utcnow() - j.updated_at).total_seconds() / 3600
                    for j in all_jobs if j.updated_at]
            if ages:
                summary["oldest_job_age_hours"] = max(ages)

        for job in all_jobs:
            summary["by_status"][job.status.value] = summary["by_status"].get(job.status.value, 0) + 1
            if job.status == UploadJobStatus.RETRY_PENDING:
                summary["retry_pending"] += 1

        return summary


def create_recovery_manager(upload_repo: UploadRepository,
                            max_processing_age_hours: int = 2) -> RecoveryManager:
    """Factory for RecoveryManager."""
    return RecoveryManager(upload_repo, max_processing_age_hours)