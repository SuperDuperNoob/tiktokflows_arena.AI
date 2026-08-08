# Operations Guide

## Overview
This guide covers day-to-day operations for the TikTok Auto-Posting Machine (Arena.AI).

## Starting the System

### Prerequisites
- Python 3.11+
- Virtual environment with dependencies installed
- Configuration file at `config/config.yaml`
- Environment variables set (see `.env.example`)

### Start the Orchestrator
```bash
cd /path/to/tiktokflows_arena.AI
export TIKTOK_MACHINE_CONFIG=config/config.yaml
export TESTING=0  # Set to 1 for test mode
python scripts/orchestrator.py
```

### Run as Service (systemd)
```ini
# /etc/systemd/system/tiktok-machine.service
[Unit]
Description=TikTok Auto-Posting Machine
After=network.target

[Service]
Type=simple
User=tiktok
WorkingDirectory=/opt/tiktok-machine
Environment=TIKTOK_MACHINE_CONFIG=/opt/tiktok-machine/config/config.yaml
Environment=TESTING=0
ExecStart=/opt/tiktok-machine/venv/bin/python scripts/orchestrator.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable tiktok-machine
sudo systemctl start tiktok-machine
```

## Stopping the System
```bash
# Graceful shutdown (SIGTERM)
sudo systemctl stop tiktok-machine

# Or if running in foreground: Ctrl+C
```

## Checking Health

### Health Check Endpoints
```bash
# Liveness check
curl http://localhost:8080/health/live

# Readiness check
curl http://localhost:8080/health/ready

# Metrics
curl http://localhost:8080/metrics
```

### Command Line Health Check
```bash
cd /path/to/tiktokflows_arena.AI
export TIKTOK_MACHINE_CONFIG=config/config.yaml
python -m scripts.operator_cli health
```

## Checking Logs
```bash
# View recent logs
tail -f logs/tiktok.log

# Search for errors
grep ERROR logs/tiktok.log

# Filter by component
grep "upload_service" logs/tiktok.log
```

## Backup Database
```bash
# Manual backup
cp logs/tiktok.db logs/backups/tiktok_$(date +%Y%m%d_%H%M%S).db

# Using operator CLI
python -m scripts.operator_cli backup-create

# List backups
python -m scripts.operator_cli backup-list

# Validate backup
python -m scripts.operator_cli backup-validate /path/to/backup.db
```

## Restore Database
```bash
# Stop service first
sudo systemctl stop tiktok-machine

# Restore from backup
cp logs/backups/tiktok_20260101_120000.db logs/tiktok.db

# Start service
sudo systemctl start tiktok-machine

# Or using operator CLI
python -m scripts.operator_cli backup-restore /path/to/backup.db
```

## Recover Failed Jobs
```bash
# List failed jobs
python -m scripts.operator_cli list-failed

# List retry-pending jobs
python -m scripts.operator_cli list-retry

# Recover a specific job
python -m scripts.operator_cli recover <job_id>

# Recover all retry-pending jobs
python -m scripts.operator_cli recover-all

# Abandon a job permanently
python -m scripts.operator_cli abandon <job_id>
```

## Renew Cookies
```bash
# Check cookie status
python -m scripts.operator_cli cookie-status

# Renew cookies via QR login
python scripts/qr_login.py <username> --uploader-dir /path/to/TiktokAutoUploader

# Or import cookies from browser export
python scripts/import_cookies.py <username> /path/to/cookies.json
```

## Monitoring Checklist (Daily)
- [ ] Check service is running: `systemctl status tiktok-machine`
- [ ] Check cookie age: `python -m scripts.operator_cli cookie-status`
- [ ] Check proxy health: `python -m scripts.operator_cli health`
- [ ] Review failed jobs: `python -m scripts.operator_cli list-failed`
- [ ] Check disk space: `df -h /path/to/tiktok-machine`
- [ ] Verify backup completed: `ls -la logs/backups/`

## Weekly Tasks
- [ ] Rotate logs if needed
- [ ] Verify backup integrity: `python -m scripts.operator_cli backup-validate`
- [ ] Check cookie expiration dates
- [ ] Review proxy performance and costs
- [ ] Update dependencies if security patches available

## Monthly Tasks
- [ ] Rotate API keys (proxy, Apify, OpenAI, Telegram)
- [ ] Vacuum database: `sqlite3 logs/tiktok.db "VACUUM;"`
- [ ] Review and update banned phrases in compliance config
- [ ] Audit logs for anomalies
- [ ] Test disaster recovery procedure

## Emergency Procedures

### Complete System Failure
1. Stop service: `sudo systemctl stop tiktok-machine`
2. Restore from latest backup: `cp logs/backups/latest.db logs/tiktok.db`
3. Restart: `sudo systemctl start tiktok-machine`
4. Verify: `python -m scripts.operator_cli health`

### Database Corruption
1. Stop service
2. Restore from last known good backup
3. Run integrity check: `sqlite3 logs/tiktok.db "PRAGMA integrity_check;"`
4. Restart service

### Cookie Expiry During Operation
1. System will log warning at 12h, error at 14h
2. Run `python scripts/qr_login.py <username>` to renew
3. Verify: `python -m scripts.operator_cli cookie-status`

### Proxy Failure
1. System will log proxy geo-check failures
2. Check proxy provider status
3. Update TIKTOK_PROXY env var with new proxy
3. Restart service

## Useful Commands Reference

| Task | Command |
|------|---------|
| Start service | `sudo systemctl start tiktok-machine` |
| Stop service | `sudo systemctl stop tiktok-machine` |
| Restart service | `sudo systemctl restart tiktok-machine` |
| View logs | `journalctl -u tiktok-machine -f` |
| Health check | `python -m scripts.operator_cli health` |
| List jobs | `python -m scripts.operator_cli list-jobs` |
| Recover job | `python -m scripts.operator_cli recover <id>` |
| Backup DB | `python -m scripts.operator_cli backup-create` |
| Restore DB | `python -m scripts.operator_cli backup-restore <file>` |
| Cookie status | `python -m scripts.operator_cli cookie-status` |
| Renew cookies | `python scripts/qr_login.py <user>` |

## Configuration Reference

Key config sections in `config/config.yaml`:
- `proxy.endpoint` - Residential proxy URL
- `ai.api_key` - OpenAI API key
- `apify.token` - Apify API token
- `telegram.bot_token` - Telegram bot token
- `posting.daily_post_target` - Daily post limit
- `logging.db_path` - Database path