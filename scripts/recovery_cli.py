#!/usr/bin/env python3
"""Recovery CLI for manual workflow recovery operations."""

import argparse
import sys
import os
from pathlib import Path

# Ensure project root in path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from services.repositories import Database, UploadRepository
from services.core.recovery_manager import RecoveryManager
from services.infrastructure.config import Config
from services.infrastructure.logging import setup_logging, get_logger

logger = get_logger("recovery_cli")


def init_recovery_manager(config_path: str) -> RecoveryManager:
    """Initialize recovery manager with config."""
    cfg = Config.get_instance(Path(config_path))
    db_path = cfg.get("logging", "db_path", default="logs/tiktok.db")
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), db_path)

    db = Database(db_path)
    upload_repo = type('UploadRepo', (), {})  # placeholder
    # Use actual UploadRepository
    from services.repositories import UploadRepository
    upload_repo = UploadRepository(db_path)
    from services.core.recovery_manager import RecoveryManager
    return RecoveryManager(upload_repo)


def cmd_list_retry(args):
    """List jobs pending retry."""
    rm = init_recovery_manager(args.config)
    jobs = rm.upload_repo.find_retry_pending_jobs(limit=args.limit)
    if not jobs:
        print("No jobs pending retry.")
        return
    print(f"{'ID':<5} {'Product':<30} {'Status':<20} {'Retries':<8} {'Updated'}")
    for job in jobs:
        print(f"{job.id:<5} {job.product_name[:30]:<30} {job.status.value:<20} {job.retry_count:<8} {job.updated_at}")


def cmd_list_dead_letter(args):
    """List dead-letter jobs."""
    from services.repositories import UploadRepository
    from services.models.upload_job import UploadJobStatus
    upload_repo = UploadRepository(os.path.join(os.path.dirname(__file__), '..', 'logs', 'tiktok.db'))
    jobs = upload_repo.find_by_status(UploadJobStatus.DEAD_LETTER, limit=args.limit)
    if not jobs:
        print("No dead-letter jobs.")
        return
    print(f"{'ID':<5} {'Product':<30} {'Error':<50} {'Retries':<8} {'Updated'}")
    for job in jobs:
        err = (job.last_error or "")[:48]
        print(f"{job.id:<5} {job.product_name[:30]:<30} {err:<50} {job.retry_count:<8} {job.updated_at}")


def cmd_recover_job(args):
    """Recover a specific job."""
    rm = init_recovery_manager(args.config)
    if rm.recover_job(args.job_id):
        print(f"Job {args.job_id} recovered successfully.")
    else:
        print(f"Failed to recover job {args.job_id}.")
        sys.exit(1)


def cmd_recover_all(args):
    """Recover all retryable jobs."""
    rm = init_recovery_manager(args.config)
    jobs = rm.upload_repo.find_retry_pending_jobs(limit=1000)
    recovered = 0
    for job in jobs:
        if rm.recover_job(job.id):
            recovered += 1
    print(f"Recovered {recovered} jobs.")


def cmd_dry_run(args):
    """Dry-run recovery: show what would be recovered."""
    rm = init_recovery_manager(args.config)
    jobs = rm.upload_repo.find_retry_pending_jobs(limit=1000)
    print(f"Would recover {len(jobs)} jobs:")
    for job in jobs:
        print(f"  Job {job.id}: {job.product_name} (retries: {job.retry_count})")


def cmd_summary(args):
    """Show workflow summary."""
    rm = init_recovery_manager(args.config)
    summary = rm.get_workflow_summary()
    print("Workflow Summary:")
    print(f"  Total unfinished: {summary['total_unfinished']}")
    print(f"  Retry pending: {summary['retry_pending']}")
    print(f"  Oldest job age: {summary['oldest_job_age_hours']:.1f} hours")
    print("  By status:")
    for status, count in summary['by_status'].items():
        print(f"    {status}: {count}")


def main():
    parser = argparse.ArgumentParser(description="Workflow recovery CLI")
    parser.add_argument("--config", default=os.path.join(os.path.dirname(__file__), "..", "config", "config.yaml"),
                        help="Path to config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-retry", help="List jobs pending retry")
    sub.add_parser("list-dead-letter", help="List dead-letter jobs")
    parser_recover = sub.add_parser("recover", help="Recover a specific job")
    parser_recover.add_argument("job_id", type=int, help="Job ID to recover")
    sub.add_parser("recover-all", help="Recover all retryable jobs")
    sub.add_parser("dry-run", help="Show what would be recovered")
    sub.add_parser("summary", help="Show workflow summary")

    args = parser.parse_args()
    setup_logging()

    if args.command == "list-retry":
        cmd_list_retry(args)
    elif args.command == "list-dead-letter":
        cmd_list_dead_letter(args)
    elif args.command == "recover":
        cmd_recover_job(args)
    elif args.command == "recover-all":
        cmd_recover_all(args)
    elif args.command == "dry-run":
        cmd_dry_run(args)
    elif args.command == "summary":
        cmd_summary(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()