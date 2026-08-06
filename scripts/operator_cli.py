#!/usr/bin/env python3
"""Operator CLI for TikTok Auto-Posting Machine.

Provides comprehensive operational tools for monitoring, recovery,
and maintenance of the TikTok automation pipeline.
"""

import argparse
import sys
import os
import json
from pathlib import Path
from datetime import datetime

# Ensure project root in path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from services.repositories import Database, UploadRepository
from services.core.recovery_manager import RecoveryManager
from services.core.metrics_service import metrics
from services.infrastructure.config import Config
from services.infrastructure.logging import setup_logging, get_logger
from services.infrastructure.health import run_health_checks, get_health_status
from services.infrastructure.diagnostics import collect_diagnostics, write_diagnostics_report
from services.infrastructure.database_backup import create_backup_manager
from services.models.upload_job import UploadJob, UploadJobStatus

logger = get_logger("operator_cli")


def init_recovery_manager(config_path: str) -> RecoveryManager:
    """Initialize recovery manager with config."""
    cfg = Config.get_instance(Path(config_path))
    db_path = cfg.get("logging", "db_path", default="logs/tiktok.db")
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), db_path)

    upload_repo = UploadRepository(db_path)
    return RecoveryManager(upload_repo)


def init_upload_repo(config_path: str) -> UploadRepository:
    """Initialize upload repository."""
    cfg = Config.get_instance(Path(config_path))
    db_path = cfg.get("logging", "db_path", default="logs/tiktok.db")
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), db_path)
    return UploadRepository(db_path)


# =============================================================================
# Job Management Commands
# =============================================================================

def cmd_list_retry(args):
    """List jobs pending retry."""
    upload_repo = init_upload_repo(args.config)
    jobs = upload_repo.find_retry_pending_jobs(limit=args.limit)
    if not jobs:
        print("No jobs pending retry.")
        return
    print(f"{'ID':<5} {'Product':<30} {'Status':<20} {'Retries':<8} {'Updated'}")
    for job in jobs:
        print(f"{job.id:<5} {job.product_name[:30]:<30} {job.status.value:<20} {job.retry_count:<8} {job.updated_at}")


def cmd_list_dead_letter(args):
    """List dead-letter jobs."""
    upload_repo = init_upload_repo(args.config)
    jobs = upload_repo.find_by_status(UploadJobStatus.DEAD_LETTER, limit=args.limit)
    if not jobs:
        print("No dead-letter jobs.")
        return
    print(f"{'ID':<5} {'Product':<30} {'Error':<50} {'Retries':<8} {'Updated'}")
    for job in jobs:
        err = (job.last_error or "")[:48]
        print(f"{job.id:<5} {job.product_name[:30]:<30} {err:<50} {job.retry_count:<8} {job.updated_at}")


def cmd_list_all(args):
    """List all jobs with optional status filter."""
    upload_repo = init_upload_repo(args.config)
    if args.status:
        try:
            status = UploadJobStatus(args.status.upper())
            jobs = upload_repo.find_by_status(status, limit=args.limit)
        except ValueError:
            print(f"Invalid status: {args.status}")
            sys.exit(1)
    else:
        jobs = upload_repo.find_unfinished_jobs()
        jobs = jobs[:args.limit]
    
    if not jobs:
        print("No jobs found.")
        return
    
    print(f"{'ID':<5} {'Product':<30} {'Status':<20} {'Retries':<8} {'Updated'}")
    for job in jobs:
        print(f"{job.id:<5} {job.product_name[:30]:<30} {job.status.value:<20} {job.retry_count:<8} {job.updated_at}")


def cmd_inspect_job(args):
    """Inspect a specific job in detail."""
    upload_repo = init_upload_repo(args.config)
    job = upload_repo.get_by_id(args.job_id)
    if not job:
        print(f"Job {args.job_id} not found.")
        sys.exit(1)
    
    print(f"Job ID: {job.id}")
    print(f"  UUID: {job.job_uuid}")
    print(f"  Product: {job.product_name} ({job.product_id})")
    print(f"  Status: {job.status.value}")
    print(f"  Video Hash: {job.video_hash}")
    print(f"  Source Path: {job.source_path}")
    print(f"  Raw Video: {job.raw_video_path}")
    print(f"  Processed: {job.processed_video_path}")
    print(f"  Caption: {job.caption_text[:80]}...")
    print(f"  Retries: {job.retry_count}/{job.max_retries}")
    print(f"  Last Error: {job.last_error or 'None'}")
    print(f"  Compliance: {job.compliance_status or 'Not checked'}")
    print(f"  Created: {job.created_at}")
    print(f"  Updated: {job.updated_at}")
    if job.posted_at:
        print(f"  Posted: {job.posted_at}")
    if job.tiktok_video_id:
        print(f"  TikTok ID: {job.tiktok_video_id}")


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


def cmd_abandon_job(args):
    """Abandon a job (mark as ABANDONED)."""
    upload_repo = init_upload_repo(args.config)
    job = upload_repo.get_by_id(args.job_id)
    if not job:
        print(f"Job {args.job_id} not found.")
        sys.exit(1)
    
    from services.core.recovery_manager import RecoveryManager
    rm = RecoveryManager(upload_repo)
    rm._abandon_job(job)
    print(f"Job {args.job_id} abandoned.")


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


# =============================================================================
# Health & Diagnostics Commands
# =============================================================================

def cmd_health(args):
    """Run health checks."""
    if args.quick:
        status = get_health_status()
        print(f"Overall health: {status}")
    else:
        result = run_health_checks()
        print(f"Overall health: {result['status']}")
        print(f"Timestamp: {result['timestamp']}")
        print()
        for name, check in result['checks'].items():
            status_icon = {"healthy": "✓", "degraded": "⚠", "unhealthy": "✗"}.get(check['status'], "?")
            print(f"  {status_icon} {name}: {check['status']} - {check['message']} ({check['duration_ms']:.1f}ms)")
            if args.verbose and check.get('details'):
                for k, v in check['details'].items():
                    print(f"    {k}: {v}")


def cmd_diagnostics(args):
    """Run diagnostics."""
    report = collect_diagnostics(include_sensitive=args.include_sensitive)
    
    if args.output:
        path = write_diagnostics_report(args.output, include_sensitive=args.include_sensitive)
        print(f"Diagnostics written to: {path}")
    else:
        print(json.dumps(report, indent=2, default=str))


def cmd_metrics(args):
    """Show metrics."""
    if args.reset:
        metrics.reset()
        print("Metrics reset.")
        return
    
    all_metrics = metrics.get_all_metrics()
    
    if args.json:
        print(json.dumps(all_metrics, indent=2, default=str))
    else:
        print("=== Counters ===")
        for name, data in all_metrics.get('counters', {}).items():
            labels = f" {data['labels']}" if data['labels'] else ""
            print(f"  {name}{labels}: {data['value']}")
        
        print("\n=== Gauges ===")
        for name, data in all_metrics.get('gauges', {}).items():
            labels = f" {data['labels']}" if data['labels'] else ""
            print(f"  {name}{labels}: {data['value']}")
        
        print("\n=== Histograms ===")
        for name, data in all_metrics.get('histograms', {}).items():
            labels = f" {data['labels']}" if data['labels'] else ""
            count = data['count']
            if count > 0:
                avg = data['sum'] / count
                print(f"  {name}{labels}: count={count}, avg={avg:.2f}, min={data['min']:.2f}, max={data['max']:.2f}")


# =============================================================================
# Backup Commands
# =============================================================================

def cmd_backup_list(args):
    """List database backups."""
    cfg = Config.get_instance(Path(args.config))
    db_path = cfg.get("logging", "db_path", default="logs/tiktok.db")
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), db_path)
    
    bm = create_backup_manager(db_path)
    backups = bm.list_backups()
    
    if not backups:
        print("No backups found.")
        return
    
    print(f"{'File':<45} {'Size (MB)':<10} {'Modified':<20} {'Schema Version'}")
    for b in backups:
        size_mb = b['size'] / (1024 * 1024)
        meta = b.get('metadata', {})
        schema = meta.get('schema_version', 'unknown')
        print(f"{b['file']:<45} {size_mb:<10.2f} {b['modified']:<20} {schema}")


def cmd_backup_create(args):
    """Create a database backup."""
    cfg = Config.get_instance(Path(args.config))
    db_path = cfg.get("logging", "db_path", default="logs/tiktok.db")
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), db_path)
    
    bm = create_backup_manager(db_path)
    backup_path = bm.create_backup(app_version=args.version)
    print(f"Backup created: {backup_path}")


def cmd_backup_validate(args):
    """Validate a backup."""
    cfg = Config.get_instance(Path(args.config))
    db_path = cfg.get("logging", "db_path", default="logs/tiktok.db")
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), db_path)
    
    bm = create_backup_manager(db_path)
    backup_path = Path(args.backup_file)
    if not backup_path.is_absolute():
        backup_path = Path("logs/backups") / args.backup_file
    
    result = bm.validate_backup(backup_path)
    print(json.dumps(result, indent=2))
    
    if not result.get('valid', False):
        sys.exit(1)


def cmd_backup_restore(args):
    """Restore database from backup."""
    cfg = Config.get_instance(Path(args.config))
    db_path = cfg.get("logging", "db_path", default="logs/tiktok.db")
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), db_path)
    
    bm = create_backup_manager(db_path)
    backup_path = Path(args.backup_file)
    if not backup_path.is_absolute():
        backup_path = Path("logs/backups") / args.backup_file
    
    if not args.force:
        confirm = input(f"Restore from {backup_path}? This will overwrite current database. [y/N]: ")
        if confirm.lower() != 'y':
            print("Cancelled.")
            return
    
    bm.restore_backup(backup_path)
    print("Database restored successfully.")


def cmd_integrity(args):
    """Check database integrity."""
    cfg = Config.get_instance(Path(args.config))
    db_path = cfg.get("logging", "db_path", default="logs/tiktok.db")
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), db_path)
    
    bm = create_backup_manager(db_path)
    result = bm.check_integrity()
    print(json.dumps(result, indent=2))
    
    if not result.get('integrity_ok', False):
        sys.exit(1)


# =============================================================================
# Configuration Commands
# =============================================================================

def cmd_config_show(args):
    """Show current configuration (sanitized)."""
    from services.infrastructure.diagnostics import get_config_summary
    config = get_config_summary()
    print(json.dumps(config, indent=2, default=str))


def cmd_config_validate(args):
    """Validate configuration."""
    from services.infrastructure.config import Config
    try:
        cfg = Config.get_instance(Path(args.config))
        config = cfg.get_section("")
        print("Configuration is valid.")
        print(f"  Sections: {list(config.keys())}")
    except Exception as e:
        print(f"Configuration invalid: {e}")
        sys.exit(1)


def cmd_secrets_audit(args):
    """Audit for exposed secrets."""
    from services.infrastructure.security_audit import audit_secrets
    result = audit_secrets(str(PROJECT_ROOT))
    auditor = type(result).__name__
    print(auditor)
    print(result.generate_report())


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="TikTok Auto-Posting Machine - Operator CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Job management
  %(prog)s list-retry
  %(prog)s list-dead-letter
  %(prog)s inspect 123
  %(prog)s recover 123
  %(prog)s recover-all
  %(prog)s abandon 123
  %(prog)s summary

  # Health & diagnostics
  %(prog)s health
  %(prog)s health --verbose
  %(prog)s diagnostics --output logs/diag.json
  %(prog)s metrics

  # Backup management
  %(prog)s backup-list
  %(prog)s backup-create
  %(prog)s backup-validate tiktok_20260115_120000.db.gz
  %(prog)s backup-restore tiktok_20260115_120000.db.gz
  %(prog)s integrity

  # Configuration
  %(prog)s config-show
  %(prog)s config-validate
  %(prog)s secrets-audit
        """
    )
    parser.add_argument("--config", default=os.path.join(os.path.dirname(__file__), "..", "config", "config.yaml"),
                        help="Path to config.yaml")
    
    sub = parser.add_subparsers(dest="command", required=True)
    
    # Job management
    sub.add_parser("list-retry", help="List jobs pending retry").add_argument("--limit", type=int, default=50)
    sub.add_parser("list-dead-letter", help="List dead-letter jobs").add_argument("--limit", type=int, default=50)
    list_all = sub.add_parser("list-all", help="List all jobs")
    list_all.add_argument("--limit", type=int, default=50)
    list_all.add_argument("--status", help="Filter by status")
    inspect = sub.add_parser("inspect", help="Inspect a specific job")
    inspect.add_argument("job_id", type=int, help="Job ID to inspect")
    recover = sub.add_parser("recover", help="Recover a specific job")
    recover.add_argument("job_id", type=int, help="Job ID to recover")
    sub.add_parser("recover-all", help="Recover all retryable jobs")
    abandon = sub.add_parser("abandon", help="Abandon a job")
    abandon.add_argument("job_id", type=int, help="Job ID to abandon")
    sub.add_parser("dry-run", help="Show what would be recovered")
    sub.add_parser("summary", help="Show workflow summary")
    
    # Health & diagnostics
    health = sub.add_parser("health", help="Run health checks")
    health.add_argument("--quick", action="store_true", help="Quick status only")
    health.add_argument("--verbose", action="store_true", help="Verbose output")
    diag = sub.add_parser("diagnostics", help="Run diagnostics")
    diag.add_argument("--output", help="Output file path")
    diag.add_argument("--include-sensitive", action="store_true", help="Include sensitive values")
    metrics_cmd = sub.add_parser("metrics", help="Show metrics")
    metrics_cmd.add_argument("--json", action="store_true", help="JSON output")
    metrics_cmd.add_argument("--reset", action="store_true", help="Reset metrics")
    
    # Backup
    sub.add_parser("backup-list", help="List database backups")
    backup_create = sub.add_parser("backup-create", help="Create database backup")
    backup_create.add_argument("--version", default="unknown", help="App version")
    backup_validate = sub.add_parser("backup-validate", help="Validate a backup")
    backup_validate.add_argument("backup_file", help="Backup file to validate")
    backup_restore = sub.add_parser("backup-restore", help="Restore database from backup")
    backup_restore.add_argument("backup_file", help="Backup file to restore from")
    backup_restore.add_argument("--force", action="store_true", help="Skip confirmation")
    sub.add_parser("integrity", help="Check database integrity")
    
    # Configuration
    sub.add_parser("config-show", help="Show current configuration (sanitized)")
    sub.add_parser("config-validate", help="Validate configuration")
    sub.add_parser("secrets-audit", help="Audit for exposed secrets")
    
    args = parser.parse_args()
    setup_logging()
    
    # Route to command handler
    commands = {
        # Jobs
        "list-retry": cmd_list_retry,
        "list-dead-letter": cmd_list_dead_letter,
        "list-all": cmd_list_all,
        "inspect": cmd_inspect_job,
        "recover": cmd_recover_job,
        "recover-all": cmd_recover_all,
        "abandon": cmd_abandon_job,
        "dry-run": cmd_dry_run,
        "summary": cmd_summary,
        # Health
        "health": cmd_health,
        "diagnostics": cmd_diagnostics,
        "metrics": cmd_metrics,
        # Backup
        "backup-list": cmd_backup_list,
        "backup-create": cmd_backup_create,
        "backup-validate": cmd_backup_validate,
        "backup-restore": cmd_backup_restore,
        "integrity": cmd_integrity,
        # Config
        "config-show": cmd_config_show,
        "config-validate": cmd_config_validate,
        "secrets-audit": cmd_secrets_audit,
    }
    
    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()