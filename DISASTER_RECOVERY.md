# TikTok Auto-Posting Machine - Disaster Recovery Plan

## Overview

This document describes the disaster recovery procedures for the TikTok Auto-Posting Machine (Arena.AI). It covers failure scenarios, detection methods, recovery procedures, and backup strategies.

---

## 1. System Architecture Summary

The system consists of:
- **Application**: Python service-oriented pipeline (scripts/orchestrator.py)
- **Database**: SQLite (logs/tiktok.db) with WAL mode
- **Storage**: Local filesystem (content/*) + Google Drive (rclone)
- **External**: TiktokAutoUploader (protected dependency), Telegram Bot, OpenAI API, Apify, Proxy
- **Monitoring**: Health checks, metrics, diagnostics, structured logging

---

## 2. Failure Scenarios

### 2.1 Machine Failure (Complete Host Loss)

**Detection:**
- Orchestrator process stops
- Systemd service enters failed state
- Health endpoint returns 503/timeout
- No metrics updates for >5 minutes

**Recovery Steps:**
1. Provision new host with same OS/dependencies
2. Restore from git repository
3. Restore database from latest backup
4. Restore content directories from Google Drive
5. Re-configure secrets (environment variables)
6. Start service

**Data Loss Risk:** Minimal (database backed up every cycle, content synced to Drive)

**RTO:** 30 minutes | **RPO:** 1 cycle (≤2 hours)

---

### 2.2 Database Corruption

**Detection:**
- `PRAGMA integrity_check` fails
- SQLite errors in logs (SQLITE_CORRUPT, disk I/O error)
- Health check `database` returns unhealthy
- Application crashes with sqlite3.DatabaseError

**Recovery Steps:**
1. Stop orchestrator: `systemctl stop tiktok-machine`
2. Verify corruption: `python -m services.infrastructure.database_backup --integrity`
3. Restore from latest valid backup:
   ```bash
   python -c "
   from services.infrastructure.database_backup import create_backup_manager
   bm = create_backup_manager('logs/tiktok.db')
   bm.restore_backup(Path('logs/backups/tiktok_20260115_120000.db.gz'))
   "
   ```
3. Verify integrity: `bm.check_integrity()`
4. Start orchestrator: `systemctl start tiktok-machine`

**Data Loss Risk:** Low (backups every cycle, WAL mode reduces corruption risk)

**RTO:** 10 minutes | **RPO:** 1 cycle (≤2 hours)

---

### 2.3 Expired/Invalid TikTok Cookies

**Detection:**
- Upload failures with "session expired" or "login required"
- Health check: cookie age > 12h warning in logs
- Upload success rate drops to 0%

**Recovery Steps:**
1. Stop orchestrator: `systemctl stop tiktok-machine`
2. Re-authenticate:
   ```bash
   cd /opt/TiktokAutoUploader
   python3 qr_login.py --username your_account
   ```
3. Verify cookies: `ls -la CookiesDir/`
4. Start orchestrator: `systemctl start tiktok-machine`

**Data Loss Risk:** None (queue preserved, retries on restart)

**RTO:** 15 minutes | **RPO:** 0

---

### 2.4 Storage Outage (Google Drive / Local Disk)

**Detection:**
- `storage` health check fails
- Sync failures in logs
- Disk usage > 90%
- rclone errors in logs

**Recovery Steps (Google Drive):**
1. Check rclone config: `rclone config show gdrive`
2. Test connectivity: `rclone lsd gdrive:`
3. Re-authenticate if needed: `rclone config reconnect gdrive`
4. Manual sync: `rclone sync content/processed gdrive:TikTok/processed --progress`

**Recovery Steps (Local Disk):**
1. Check disk space: `df -h`
2. Clean old files: `find content/processed -mtime +30 -delete`
3. Check permissions: `ls -la content/`
4. If disk failed: replace disk, restore from Google Drive

**Data Loss Risk:** Low (local content synced to Drive, Drive is source of truth)

**RTO:** 20 minutes | **RPO:** 0

---

### 2.5 Proxy Outage

**Detection:**
- `proxy` health check fails
- Upload failures with proxy errors
- Geo check returns non-Malaysian IP
- Proxy health check logs "unreachable"

**Recovery Steps:**
1. Check proxy provider status
2. Test proxy manually:
   ```bash
   curl -x http://user:pass@host:port http://ip-api.com/json
   ```
3. Update proxy endpoint in config.yaml or TIKTOK_PROXY env var
4. If strict_mode enabled: orchestrator will pause until proxy fixed
5. Restart if config changed: `systemctl reload tiktok-machine` (SIGHUP)

**Data Loss Risk:** None (queue preserved, retries on proxy recovery)

**RTO:** 10 minutes | **RPO:** 0

---

### 2.6 Network Outage

**Detection:**
- `network` health checks fail
- Multiple external endpoints unreachable
- Upload failures with connection errors

**Recovery Steps:**
1. Check host network: `ping 8.8.8.8`, `curl -I https://google.com`
2. Check firewall/security groups
3. Check DNS: `dig api.tiktok.com`
4. If host issue: contact infrastructure provider
5. System auto-retries on network recovery (retry framework)

**Data Loss Risk:** None (queue preserved)

**RTO:** Depends on infrastructure | **RPO:** 0

---

### 2.7 Configuration Error

**Detection:**
- Orchestrator fails to start
- Config validation errors in logs
- Health check `config` returns degraded/unhealthy

**Recovery Steps:**
1. Check logs for validation errors
2. Fix config.yaml or environment variables
3. Validate: `python -m scripts.operator_cli --config config/config.yaml config-validate`
4. Reload: `systemctl kill -s SIGHUP tiktok-machine`

**Data Loss Risk:** None

**RTO:** 5 minutes | **RPO:** 0

---

### 2.8 AI Service Outage (OpenAI/Apify)

**Detection:**
- `ai` metric shows failures
- AI growth analysis fails
- Daily jobs fail with AI errors

**Recovery Steps:**
1. Check API status pages
2. Verify API keys valid
3. Check quota/billing
4. System continues without AI (cached analysis, no growth calls)
5. Auto-recovers when service restores

**Data Loss Risk:** Low (1 AI call/day cached)

**RTO:** Depends on provider | **RPO:** 0

---

## 3. Backup Strategy

### 3.1 Database Backups

| Aspect | Detail |
|--------|--------|
| Frequency | Every upload cycle (on success) + manual |
| Retention | 30 backups (configurable) |
| Format | Compressed SQL dump (.db.gz) + metadata JSON |
| Location | logs/backups/ (local) |
| Verification | Automatic on restore, manual via `backup-validate` |

### 3.2 Content Backups

| Aspect | Detail |
|--------|--------|
| Raw Videos | Google Drive (source of truth) |
| Processed Videos | Google Drive (synced after upload) |
| Sidecars | Google Drive (synced with videos) |
| Frequency | After every upload cycle |

### 3.3 Configuration Backups

| Aspect | Detail |
|--------|--------|
| Config | Git repository (config.yaml tracked) |
| Secrets | Environment variables (not in git) |
| Cookies | TiktokAutoUploader/CookiesDir/ (manual backup) |

---

## 4. Recovery Procedures Summary

### 4.1 Quick Reference Commands

```bash
# Health check
python -m scripts.operator_cli health

# Full diagnostics
python -m scripts.operator_cli diagnostics --output logs/diag.json

# Database integrity
python -m scripts.operator_cli integrity

# List backups
python -m scripts.operator_cli backup-list

# Create backup
python -m scripts.operator_cli backup-create

# Restore backup
python -m scripts.operator_cli backup-restore tiktok_20260115_120000.db.gz

# Job recovery
python -m scripts.operator_cli list-retry
python -m scripts.operator_cli recover 123
python -m scripts.operator_cli recover-all

# Secrets audit
python -m scripts.operator_cli secrets-audit
```

### 4.2 Recovery Decision Tree

```
START: System Alert
    │
    ├─► Health Check Failed?
    │     ├─ Database → Restore from backup
    │     ├─ Proxy → Check/Update proxy endpoint
    │     ├─ Storage → Check rclone/Disk space
    │     ├─ Config → Fix config, SIGHUP reload
    │     └─ Network → Check infrastructure
    │
    ├─ Upload Failures?
    │     ├─ Cookie expired → qr_login.py
    │     ├─ Proxy → Update proxy
    │     ├─ Compliance → Check content
    │     └─ Retry → Check retry queue
    │
    ├─ Process Down?
    │     └─ systemctl restart tiktok-machine
    │
    └─ Data Corruption?
          └─ Restore database from backup
```

---

## 5. Testing Schedule

| Test | Frequency | Method |
|------|-----------|--------|
| Backup Restore | Monthly | `backup-restore` to test DB |
| Integrity Check | Weekly | `integrity` command |
| Cookie Validity | Daily | Auto-checked by orchestrator |
| Proxy Health | Per cycle | Auto-checked by orchestrator |
| DR Drill | Quarterly | Full restore to staging |

---

## 6. Communication Plan

| Severity | Notification | Escalation |
|----------|--------------|------------|
| Critical (Down) | Immediate (Telegram/Alert) | On-call within 15 min |
| Warning (Degraded) | Within 1 hour | On-call within 4 hours |
| Info (Recovered) | Next business day | N/A |

---

## 7. Contacts

| Role | Contact | Backup |
|------|---------|--------|
| Primary On-call | [Name/Phone] | [Name/Phone] |
| DevOps | [Name/Phone] | [Name/Phone] |
| Proxy Provider | [Support URL] | N/A |
| Infrastructure | [Cloud Provider Support] | N/A |

---

## 8. Post-Incident Process

1. **Incident Report** - Document timeline, root cause, impact
2. **Action Items** - Preventive measures, automation opportunities
3. **Runbook Update** - Update this document with lessons learned
4. **Review** - Team review within 1 week

---

*Last Updated: 2026-08-06*
*Version: 1.0*
*Next Review: 2026-11-06*