# Production Readiness Checklist — Phase 15

**Date:** 2026-08-09
**Branch:** main
**Status:** READY FOR REVIEW

---

## ✅ Deployment Requirements

### System Requirements
| Component | Requirement | Status |
|-----------|-------------|--------|
| OS | Linux (tested on 7.0.13+parrot7-amd64) | ✅ |
| Python | 3.11+ (running 3.13.5) | ✅ |
| Memory | 4GB+ recommended | ✅ |
| Disk | 20GB+ for content + DB + logs | ✅ |
| Network | Outbound HTTPS (TikTok, Google Drive, Apify, AI, Telegram, ip-api.com, ipinfo.io) | ✅ |

### Python Dependencies
- All pinned in `requirements.pinned.txt`
- Virtualenv at `venv/`
- Key packages: `python-telegram-bot`, `fastapi`, `uvicorn`, `requests`, `pyyaml`, `rclone`, `ffmpeg-python`, `playwright`, `sqlite3` (stdlib)

### External Services
| Service | Purpose | Auth Method | Configured |
|---------|---------|-------------|------------|
| TikTok Web API | Video upload | Session cookies | ⚠️ Manual QR login |
| Google Drive (rclone) | Content sync | OAuth token | ⚠️ Manual rclone config |
| Telegram Bot API | Notifications & control | Bot token | ✅ Via env/config |
| OpenAI-compatible API | Captions, compliance, strategy | API key | ✅ Via env/config |
| Apify (clockworks/tiktok-scraper) | Competitor scraping | API token | ✅ Via env/config |
| ip-api.com / ipinfo.io | Proxy geo verification | Free tier | ✅ Built-in |
| Cloudflare Tunnel | Web access (no open ports) | Tunnel token | ✅ deploy/cloudflared.service |

---

## ✅ Installation

```bash
# 1. Clone repository
git clone <repo> /opt/tiktok-machine
cd /opt/tiktok-machine

# 2. Create virtualenv
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.pinned.txt

# 4. Install Playwright browsers
playwright install chromium

# 5. Install system dependencies
apt-get update && apt-get install -y ffmpeg rclone sqlite3

# 6. Configure rclone for Google Drive
rclone config  # Create remote named "gdrive"

# 7. Create config file
cp config/config.yaml.example config/config.yaml
# Edit config.yaml with real values (or use env vars)

# 8. Initialize database
TESTING=1 TIKTOK_MACHINE_CONFIG=config/config.yaml python -m scripts.setup_tools init-db

# 9. Seed caption pool
TESTING=1 TIKTOK_MACHINE_CONFIG=config/config.yaml python -m scripts.setup_tools seed-captions

# 10. Test proxy
TESTING=1 TIKTOK_MACHINE_CONFIG=config/config.yaml python -m scripts.setup_tools test-proxy

# 11. Login to TikTok (QR code via proxy)
TESTING=1 TIKTOK_MACHINE_CONFIG=config/config.yaml python scripts/qr_login.py kumpul.shop --proxy "user:pass@host:port"

# 12. Install systemd services
sudo cp deploy/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tiktok-orchestrator tiktok-webapp tiktok-cloudflared
```

---

## ✅ Configuration

### Required Config (config.yaml or env vars)
```yaml
# Minimum required for production
tiktok:
  session_username: "your-shop-name"
  uploader_dir: "/opt/tiktok-machine/TiktokAutoUploader"

proxy:
  endpoint: "user:pass@host:port"  # Malaysian residential/4G proxy REQUIRED
  strict_mode: true
  geo_check: true

ai:
  api_key: "sk-..."  # OpenAI-compatible
  base_url: "https://api.iamhc.cn/v1"
  enable_ai: true

telegram:
  bot_token: "123:..."
  allowed_user_id: 123456789

google_drive:
  rclone_remote: "gdrive"
  remote_path: "TikTokContent"

apify:
  token: "apify_api_..."
```

### Environment Variables (Alternative to config.yaml secrets)
```bash
export TIKTOK_PROXY="user:pass@host:port"
export AI_API_KEY="sk-..."
export TELEGRAM_BOT_TOKEN="123:..."
export TELEGRAM_ALLOWED_USER_ID="123456789"
export APIFY_TOKEN="apify_api_..."
```

---

## ✅ Operations

### Startup
```bash
# Start all services
sudo systemctl start tiktok-cloudflared
sudo systemctl start tiktok-orchestrator
sudo systemctl start tiktok-webapp

# Check status
sudo systemctl status tiktok-orchestrator
sudo journalctl -u tiktok-orchestrator -f
```

### Orchestrator Startup Sequence
1. Load config (`services.infrastructure.config.Config`)
2. Initialize database (WAL mode, schema migrations)
3. Initialize repositories and services
4. Run startup validation:
   - Database connectivity
   - Required directories exist
   - Upload queue consistency (no orphaned .mp4 without sidecar)
5. Run recovery reconciliation (recover UPLOADING/PROCESSING jobs)
6. Enter main loop (2h ±30min, quiet 2-6 AM MYT)

### Shutdown
```bash
# Graceful shutdown (SIGTERM)
sudo systemctl stop tiktok-orchestrator

# Orchestrator handles:
# 1. Flush logs
# 2. Close database connections
# 3. Wait for in-progress operations (30s timeout)
```

### Monitoring
| Check | Command | Expected |
|-------|---------|----------|
| Orchestrator running | `systemctl status tiktok-orchestrator` | active (running) |
| Recent posts | `sqlite3 logs/tiktok.db "SELECT * FROM posts ORDER BY posted_at DESC LIMIT 5"` | POSTED entries |
| Queue depth | `ls content/processed/*.mp4 \| wc -l` | 0-5 typically |
| Stock levels | `sqlite3 logs/tiktok.db "SELECT product_name, COUNT(*) FROM raw_stock WHERE posted_at IS NULL GROUP BY product_name"` | >5 per product |
| Cookie age | `stat TiktokAutoUploader/CookiesDir/tiktok_session-*.cookie` | <14 days |
| Proxy health | `curl -x "http://user:pass@host:port" https://ipinfo.io/json` | Country: MY |

### Health Check Endpoint
```bash
# Via webapp (if running)
curl http://localhost:8080/api/health

# Via operator CLI
python -m scripts.operator_cli health
```

### Logs
| Log File | Purpose | Rotation |
|----------|---------|----------|
| `logs/tiktok.log` | Structured application logs | 10MB × 5 files |
| `logs/tiktok.db` | SQLite database | Manual backup |
| `logs/burn_log.jsonl` | VideoProcessor audit | Manual |
| `logs/success.log` | Successful uploads | Manual |
| `logs/failed.log` | Failed uploads | Manual |
| `logs/deleted.log` | Raw archive audit | Manual |
| `logs/growth_report.txt` | AI growth output | Overwritten daily |
| `logs/daily_report.txt` | OPS report | Overwritten daily |
| `logs/drive_cleanup.log` | sync_out audit | Manual |

---

## ✅ Recovery

### Backup
```bash
# Create backup
python -m scripts.operator_cli backup

# Creates: logs/backups/tiktok_YYYYMMDD_HHMMSS.db + .meta.json
# Includes: Schema version, table row counts, checksums
```

### Restore
```bash
# List backups
python -m scripts.operator_cli backup --list

# Restore specific backup
python -m scripts.operator_cli restore logs/backups/tiktok_20260801_030000.db

# Restore latest
python -m scripts.operator_cli restore --latest
```

### Failed Jobs
```bash
# List retry queue
python -m scripts.operator_cli list-retry

# List dead letter queue
python -m scripts.operator_cli list-dead-letter

# Retry specific job
python -m scripts.operator_cli retry <job_id>

# Re-process dead letter
python -m scripts.operator_cli reprocess <job_id>
```

### Cookie Renewal (Every ~14 Days)
```bash
# Option 1: QR login via proxy (recommended)
python scripts/qr_login.py kumpul.shop --proxy "user:pass@host:port" --timeout 120

# Option 2: Import cookies from browser
python scripts/import_cookies.py --browser chrome --profile Default --uploader-dir /opt/tiktok-machine/TiktokAutoUploader

# Verify
python -m scripts.setup_tools cookie-status
```

---

## ✅ Maintenance

### Updates
```bash
# 1. Pull latest
git pull origin main

# 2. Update dependencies (if requirements changed)
pip install -r requirements.pinned.txt

# 3. Run migrations (auto on orchestrator restart)
# Schema version tracked in schema_version table

# 4. Restart services
sudo systemctl restart tiktok-orchestrator tiktok-webapp
```

### Migrations
- Automatic on orchestrator startup
- Versioned in `schema_version` table
- Current version: 4
- Run manually: `python -m scripts.setup_tools migrate`

### Daily Jobs (3 AM MYT)
1. **Competitor scrape** → `competitor_videos`, `competitor_daily`
2. **Metrics reconcile** → Match uploads to scraped data via caption/time
3. **Daily report** → `daily_report.txt` (stock, posted, performance)
4. **Growth (if /growth triggered)** → `growth_report.txt` + `preset_text.txt`

### Manual Daily Job Trigger
```bash
TESTING=1 TIKTOK_MACHINE_CONFIG=config/config.yaml python scripts/competitor_scraper.py
TESTING=1 TIKTOK_MACHINE_CONFIG=config/config.yaml python scripts/reconcile_metrics.py
TESTING=1 TIKTOK_MACHINE_CONFIG=config/config.yaml python scripts/generate_report.py
TESTING=1 TIKTOK_MACHINE_CONFIG=config/config.yaml python scripts/ai_growth.py --ai
```

---

## ⚠️ Known Limitations

| Limitation | Impact | Workaround |
|------------|--------|------------|
| **TikTok API dependency** | TiktokAutoUploader is external; breaking changes possible | Pin TiktokAutoUploader commit; monitor for updates |
| **Single-machine architecture** | No horizontal scaling; orchestrator is single-threaded | Vertical scaling only; consider task queue for future |
| **SQLite write throughput** | WAL mode handles concurrent reads; writes serialized | Acceptable for ~10 posts/day; not for high volume |
| **No retry queue for failed uploads** | Transient failures require manual re-queue | Operator CLI `retry` command; monitor failed.log |
| **Residential proxy required** | Without MY proxy: 0-view shadowban risk | Budget for reliable Malaysian residential/4G proxy |
| **Cookie expiry** | Manual re-login every ~14 days | Calendar reminder; automate with cron + qr_login.py |
| **No message queue** | No durable job persistence across crashes | RecoveryManager handles UPLOADING/PROCESSING on restart |
| **Single Drive remote** | One rclone remote for all content | N/A |
| **No multi-account support** | Single TikTok session | Run separate instances for multiple accounts |

---

## 🔒 Security Posture

| Control | Status |
|---------|--------|
| Non-root system user | ✅ `tiktok` user in deploy/setup.sh |
| Telegram authorization | ✅ Single allowed_user_id |
| Web behind Cloudflare Tunnel | ✅ No open ports |
| Secrets in config.yaml (git-ignored) | ✅ Placeholders only |
| Secrets masked in API responses | ✅ webapp/server.py mask_secret() |
| Diagnostics mask secrets | ✅ SecretMasker in diagnostics.py |
| Proxy credentials only for TikTok upload | ✅ Not used for AI/Telegram/Apify/Drive |
| Cookie files permissions | ⚠️ Documented 600/700, not enforced |
| Database no plaintext secrets | ✅ |
| Backup excludes secrets | ✅ SQL dump only |
| Review package excludes secrets | ✅ logs/, cookies/, .git/, __pycache__ excluded |

---

## 📊 Performance Baselines

| Operation | Duration |
|-----------|----------|
| Unit test suite (62 tests) | 6-7 seconds |
| Orchestrator startup | ~2 seconds |
| Health check (all 6) | ~150ms |
| Diagnostics collection | ~500ms |
| Database backup | ~200ms |
| Backup validation | ~300ms |
| Video encode (typical 30s clip) | 30-60 seconds |
| TikTok upload (via proxy) | 10-30 seconds |
| Competitor scrape (Apify) | 30-60 seconds |
| Metrics reconcile | <5 seconds |
| Daily report generation | <2 seconds |

---

## ✅ Final Verification

```bash
# All tests pass
TESTING=1 TIKTOK_MACHINE_CONFIG=config/config.yaml python -m pytest tests/ -v
# → 62 passed

# Orchestrator starts cleanly
TESTING=1 TIKTOK_MACHINE_CONFIG=config/config.yaml timeout 10 python scripts/orchestrator.py
# → Startup validation OK, reconciliation OK, main loop enters

# Config validation works
TESTING=1 TIKTOK_MACHINE_CONFIG=config/config.yaml python -c "from services.infrastructure.config import Config; Config(Path('config/config.yaml'))"
# → No ConfigError

# Services import without cycles
python -c "from services.core import VideoService, UploadService, StorageService, AnalyticsService, SchedulerService, ProductService, ProxyService; print('OK')"
# → OK

# Recovery manager works
python -c "from services.core.recovery_manager import RecoveryManager; from services.repositories import UploadRepository; from services.infrastructure.database import Database; db=Database('logs/tiktok.db'); rm=RecoveryManager(UploadRepository(db.db_path)); print(rm.run_startup_reconciliation())"
# → Reconciliation result
```

---

## 📋 Sign-off Checklist

- [x] All tests passing (62/62)
- [x] Architecture documentation matches implementation
- [x] Configuration audit complete
- [x] Dead code audit complete (no uncertain removals)
- [x] Security review complete
- [x] Documentation accuracy verified
- [x] Deployment guide tested
- [x] Operations guide tested
- [x] Recovery procedures tested
- [x] Known limitations documented honestly
- [x] Review package created (phase_15_review.zip)

---

**Verdict:** **READY FOR ARCHITECTURAL REVIEW**

The system is production-ready with documented manual steps (rclone config, TikTok cookie login, proxy procurement). All automated components are tested and verified. The architecture is clean with proper separation of concerns, dependency injection, and no circular dependencies.