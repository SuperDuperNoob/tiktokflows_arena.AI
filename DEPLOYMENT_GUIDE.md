# TikTok Auto-Posting Machine - Deployment Guide

## Overview

This document describes the production deployment of the TikTok Auto-Posting Machine (Arena.AI). The system is a service-oriented TikTok content automation pipeline with video processing, upload scheduling, compliance checking, analytics, and monitoring.

---

## 1. Installation

### 1.1 System Requirements

| Component | Requirement |
|-----------|-------------|
| OS | Linux (Ubuntu 22.04+ / Debian 12+ recommended) |
| Python | 3.11+ |
| Memory | 2 GB minimum (4 GB recommended) |
| Disk | 20 GB minimum (SSD recommended) |
| Network | Stable internet connection |

### 1.2 System Dependencies

```bash
# Ubuntu/Debian
sudo apt-get update && sudo apt-get install -y \
    python3 python3-venv python3-dev \
    ffmpeg \
    rclone \
    sqlite3 \
    git \
    curl \
    build-essential \
    libssl-dev libffi-dev \
    fonts-noto-color-emoji \
    fonts-dejavu-core
```

### 1.3 Python Environment

```bash
# Clone repository
git clone https://github.com/SuperDuperNoob/tiktokflows_arena.AI.git
cd tiktokflows_arena.AI

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 1.4 Directory Structure

```
/opt/tiktokflows_arena.AI/          # Application root
├── config/
│   └── config.yaml                 # Main configuration
├── scripts/                        # Entry points
│   ├── orchestrator.py            # Main orchestrator
│   ├── recovery_cli.py            # Recovery operations
│   └── ...
├── services/                       # Service layer
│   ├── core/                      # Core services
│   ├── repositories/              # Data access
│   ├── infrastructure/            # External adapters
│   ├── models/                    # Domain models
│   └── utils/                     # Utilities
├── logs/                           # Log files
│   ├── tiktok.log                 # Main log
│   ├── tiktok.db                  # SQLite database
│   └── backups/                   # Database backups
├── content/
│   ├── raw/                       # Raw video files
│   ├── processed/                 # Processed videos
│   ├── queue/                     # Upload queue
│   ├── failed/                    # Failed uploads
│   └── sidecars/                  # Metadata sidecars
└── TiktokAutoUploader/            # Protected external dependency
```

---

## 2. Configuration

### 2.1 Main Configuration (`config/config.yaml`)

```yaml
# Required sections (all must be present)
telegram:
  bot_token: "YOUR_BOT_TOKEN"          # Required: Telegram bot token
  allowed_user_id: 123456789           # Required: Admin user ID

proxy:
  endpoint: "http://user:pass@host:port"  # Required: Malaysian residential proxy
  strict_mode: true                     # Fail if proxy not Malaysian
  geo_check: true                       # Verify proxy geo location

tiktok:
  session_username: "your_account"      # Required: TikTok username
  uploader_dir: "/opt/TiktokAutoUploader"

ai:
  enable_ai: true
  api_key: "YOUR_OPENAI_API_KEY"        # Required if enable_ai: true
  model: "gpt-4o-mini"
  max_calls_per_day: 1

posting:
  daily_post_target: 7
  interval_minutes: 120
  quiet_hours_start: 22
  quiet_hours_end: 8

content:
  input_dir: "content/raw"
  output_dir: "content/processed"
  processed_dir: "content/processed"
  sidecar_dir: "content/sidecars"
  min_duration: 3
  max_duration: 180
  required_hashtags: ["#fyp", "#tiktok"]
  banned_keywords: ["guaranteed", "miracle"]

encoding:
  crf: 23
  preset: "medium"

analytics:
  apify_token: "YOUR_APIFY_TOKEN"
  competitor_handles: ["competitor1", "competitor2"]
  scrape_schedule_hour: 3

google_drive:
  remote_name: "gdrive"
  sync_interval_hours: 6

logging:
  level: "INFO"
  file: "logs/tiktok.log"
  db_path: "logs/tiktok.db"
  max_bytes: 10485760
  backup_count: 5
  json_format: false

timezone: "Asia/Kuala_Lumpur"
```

### 2.2 Environment Variable Overrides

All configuration values can be overridden via environment variables:

```bash
export TIKTOK_PROXY="http://user:pass@host:port"
export TIKTOK_PROXY_STRICT=true
export TIKTOK_PROXY_GEO_CHECK=true
export OPENAI_API_KEY="your_key"
export TELEGRAM_BOT_TOKEN="your_token"
```

### 2.3 Secrets Management

**Never commit secrets to version control.** Use environment variables or a secrets manager:

```bash
# Option 1: Environment variables (recommended)
export OPENAI_API_KEY="sk-..."
export TELEGRAM_BOT_TOKEN="123:..."
export APIFY_TOKEN="apify_..."

# Option 2: .env file (not committed)
echo "OPENAI_API_KEY=sk-..." > .env
echo "TELEGRAM_BOT_TOKEN=123:..." >> .env
# Add to .gitignore: .env
```

### 2.4 TikTok Cookie Setup

```bash
# Login to TikTok (run once)
cd /opt/TiktokAutoUploader
python3 qr_login.py --username your_account

# Or import existing cookies
python3 import_cookies.py --cookie-file /path/to/cookies.txt
```

---

## 3. Running

### 3.1 Start Commands

```bash
# Development
cd /opt/tiktokflows_arena.AI
source .venv/bin/activate
TIKTOK_MACHINE_CONFIG=config/config.yaml python scripts/orchestrator.py

# Production (systemd service)
sudo systemctl start tiktok-machine
```

### 3.2 Systemd Service (Production)

Create `/etc/systemd/system/tiktok-machine.service`:

```ini
[Unit]
Description=TikTok Auto-Posting Machine
After=network.target

[Service]
Type=simple
User=tiktok
WorkingDirectory=/opt/tiktokflows_arena.AI
Environment=TIKTOK_MACHINE_CONFIG=/opt/tiktokflows_arena.AI/config/config.yaml
Environment=PATH=/opt/tiktokflows_arena.AI/.venv/bin:/usr/bin
ExecStart=/opt/tiktokflows_arena.AI/.venv/bin/python scripts/orchestrator.py
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal

# Security
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/opt/tiktokflows_arena.AI/logs /opt/tiktokflows_arena.AI/content

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable tiktok-machine
sudo systemctl start tiktok-machine
sudo systemctl status tiktok-machine
```

### 3.3 Stop/Restart Procedures

```bash
# Graceful stop (SIGTERM - allows graceful shutdown)
sudo systemctl stop tiktok-machine

# Force stop (SIGKILL - only if stuck)
sudo systemctl kill -s SIGKILL tiktok-machine

# Restart
sudo systemctl restart tiktok-machine

# Reload config without restart (SIGHUP)
sudo systemctl kill -s SIGHUP tiktok-machine
```

---

## 4. Recovery Procedures

### 4.1 Failed Jobs

```bash
# List retry queue
python scripts/recovery_cli.py --config config/config.yaml list-retry

# List dead-letter queue
python scripts/recovery_cli.py --config config/config.yaml list-dead-letter

# Recover specific job
python scripts/recovery_cli.py --config config/config.yaml recover <job_id>

# Recover all retryable jobs
python scripts/recovery_cli.py --config config/config.yaml recover-all

# Dry run (see what would be recovered)
python scripts/recovery_cli.py --config config/config.yaml dry-run

# Show workflow summary
python scripts/recovery_cli.py --config config/config.yaml summary
```

### 4.2 Database Restore

```bash
# List available backups
ls -la logs/backups/

# Validate backup
python -c "
from services.infrastructure.database_backup import create_backup_manager
bm = create_backup_manager('logs/tiktok.db')
result = bm.validate_backup(Path('logs/backups/tiktok_20260115_120000.db.gz'))
print(result)
"

# Restore from backup
python -c "
from services.infrastructure.database_backup import create_backup_manager
bm = create_backup_manager('logs/tiktok.db')
bm.restore_backup(Path('logs/backups/tiktok_20260115_120000.db.gz'))
print('Restored successfully')
"
```

### 4.3 Backup Verification

```bash
# Check database integrity
python -c "
from services.infrastructure.database_backup import create_backup_manager
bm = create_backup_manager('logs/tiktok.db')
result = bm.check_integrity()
print(result)
"

# Create manual backup
python -c "
from services.infrastructure.database_backup import create_backup_manager
bm = create_backup_manager('logs/tiktok.db')
backup_path = bm.create_backup(app_version='1.0.0')
print(f'Backup created: {backup_path}')
"
```

---

## 5. Maintenance

### 5.1 Log Management

```bash
# View logs
sudo journalctl -u tiktok-machine -f

# View application logs
tail -f logs/tiktok.log

# Rotate logs (automatic via logging config)
# Logs rotate at 10MB, keep 5 backups
```

### 5.2 Cleanup

```bash
# Clean old processed videos (keep last 30 days)
find content/processed -type f -name "*.mp4" -mtime +30 -delete

# Clean old failed uploads
find content/failed -type f -mtime +7 -delete

# Clean old backups (keep last 30)
# Automatic via backup rotation (max 30 backups)
```

### 5.3 Updates

```bash
# Pull latest changes
cd /opt/tiktokflows_arena.AI
git pull origin main

# Update dependencies
source .venv/bin/activate
pip install -r requirements.txt

# Run tests
TIKTOK_MACHINE_CONFIG=config/config.yaml TESTING=1 python -m pytest tests/ -v

# Restart service
sudo systemctl restart tiktok-machine
```

### 5.4 Health Checks

```bash
# Quick health check
python -c "
from services.infrastructure.health import get_health_status
print(get_health_status())
"

# Full health report
python -c "
from services.infrastructure.health import run_health_checks
import json
result = run_health_checks()
print(json.dumps(result, indent=2))
"

# Diagnostics
python -c "
from services.infrastructure.diagnostics import print_diagnostics
print_diagnostics()
"
```

---

## 6. Monitoring

### 6.1 Key Metrics

The system exposes metrics via the metrics service:

```python
from services.core.metrics_service import metrics

# Get all metrics
all_metrics = metrics.get_all_metrics()

# Key metrics:
# - jobs_started, jobs_completed, jobs_failed, jobs_skipped
# - upload_attempts, retries
# - upload_duration_ms, processing_time_ms
# - queue_size, storage_sync_duration_ms
# - ai_calls_total, proxy_checks_total
# - duplicate_prevented, recovery_actions
```

### 6.2 Health Endpoints (for external monitoring)

```bash
# Quick status
python -c "from services.infrastructure.health import get_health_status; print(get_health_status())"

# Full health
python -c "
from services.infrastructure.health import run_health_checks
import json
print(json.dumps(run_health_checks(), indent=2))
"
```

### 6.3 Alerting Rules (Prometheus/Alertmanager)

```yaml
# Example alerting rules
groups:
  - name: tiktok-machine
    rules:
      - alert: TikTokMachineDown
        expr: up{job="tiktok-machine"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "TikTok Machine is down"

      - alert: HighFailureRate
        expr: rate(jobs_failed_total[5m]) > 0.5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High upload failure rate"

      - alert: QueueBacklog
        expr: queue_size > 10
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Upload queue backlog"

      - alert: DatabaseCorruption
        expr: health_status{component="database"} != "healthy"
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Database health check failed"
```

---

## 7. Troubleshooting

### 7.1 Common Issues

| Issue | Detection | Resolution |
|-------|-----------|------------|
| Upload fails | `jobs_failed` metric increases | Check proxy, cookies, network |
| Cookie expired | `cookie_warning` in logs | Re-run `qr_login.py` |
| Proxy not Malaysian | `proxy_geo_check` fails | Update proxy endpoint |
| Database locked | `database` health check fails | Check for stuck processes |
| Disk full | `disk_usage_pct` > 90% | Clean old files, expand disk |
| AI quota exceeded | `ai_quota_exceeded` errors | Wait for daily reset |

### 7.2 Debug Commands

```bash
# Run diagnostics
python scripts/recovery_cli.py --config config/config.yaml summary

# Check specific job
python -c "
from services.repositories import UploadRepository
repo = UploadRepository('logs/tiktok.db')
job = repo.get_by_id(123)
print(job)
"

# Test proxy
python -c "
from services.utils.proxy import check_proxy_exit
from services.infrastructure.config import get_config
cfg = get_config()
proxy = cfg.get('proxy', 'endpoint')
print(check_proxy_exit(proxy))
"
```

---

## 8. Security Checklist

- [ ] All secrets in environment variables (not config.yaml)
- [ ] Config file permissions: `chmod 600 config/config.yaml`
- [ ] Database permissions: `chmod 600 logs/tiktok.db`
- [ ] Cookie file permissions: `chmod 600 TiktokAutoUploader/CookiesDir/*`
- [ ] Log file permissions: `chmod 640 logs/tiktok.log`
- [ ] Backup directory permissions: `chmod 700 logs/backups/`
- [ ] Service runs as non-root user
- [ ] Firewall restricts unnecessary ports
- [ ] Regular security updates applied
- [ ] Secrets rotated periodically (API keys, tokens)

---

## 9. Rollback Procedure

```bash
# 1. Stop service
sudo systemctl stop tiktok-machine

# 2. Restore database from backup
python -c "
from services.infrastructure.database_backup import create_backup_manager
bm = create_backup_manager('logs/tiktok.db')
bm.restore_backup(Path('logs/backups/tiktok_20260115_120000.db.gz'))
"

# 3. Revert code if needed
cd /opt/tiktokflows_arena.AI
git checkout <previous_tag>

# 4. Restart
sudo systemctl start tiktok-machine

# 5. Verify
python -c "from services.infrastructure.health import get_health_status; print(get_health_status())"
```

---

## 10. Support Contacts

- **System Administrator**: [Contact Info]
- **DevOps**: [Contact Info]
- **On-call**: [Contact Info]
- **Documentation**: This guide + inline code documentation