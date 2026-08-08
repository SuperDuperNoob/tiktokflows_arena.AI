# Troubleshooting Guide

## Quick Diagnostics

### Run Health Check
```bash
export TIKTOK_MACHINE_CONFIG=config/config.yaml
python -m scripts.operator_cli health
```

### Check Service Status
```bash
systemctl status tiktok-machine
journalctl -u tiktok-machine -f
```

### View Recent Logs
```bash
tail -100 logs/tiktok.log
grep -i error logs/tiktok.log | tail -20
```

## Common Issues

### 1. Service Won't Start

#### Symptom: Service fails immediately
```
systemctl status tiktok-machine
# Shows: Failed with result 'exit-code'
```

**Diagnosis:**
```bash
# Check logs
journalctl -u tiktok-machine -n 50

# Test manually
cd /path/to/tiktokflows_arena.AI
export TIKTOK_MACHINE_CONFIG=config/config.yaml
export TESTING=0
python scripts/orchestrator.py
```

**Common Causes:**
| Cause | Solution |
|-------|----------|
| Config file missing | Verify `config/config.yaml` exists |
| Python path issues | Check `PYTHONPATH` includes project root |
| Missing dependencies | Run `pip install -r requirements.txt` |
| Permission denied | Fix file permissions: `chmod 600 config/config.yaml` |

### 2. Proxy Issues

#### Proxy Geo-Check Fails
```
WARNING upload_service [-]: Proxy geo check failed: ip-api: HTTPConnectionPool...
```

**Diagnosis:**
```bash
# Test proxy manually
export TIKTOK_PROXY="http://user:pass@host:port"
python -m scripts.setup_tools test_proxy
```

**Common Causes:**
| Cause | Solution |
|-------|----------|
| Proxy down | Contact proxy provider |
| Wrong country | Verify proxy exits in Malaysia |
| Datacenter IP | Use residential/4G proxy only |
| Proxy auth failed | Check username/password |
| Port blocked | Check firewall rules |

#### Proxy Strict Mode Aborts
```
ERROR upload_service [-]: STRICT: aborting BEFORE upload - a bad exit would burn metered proxy GB...
```

**Solution:**
- Fix proxy geo-check (see above)
- Or disable strict mode temporarily: `proxy.strict_mode: false` in config.yaml

### 3. Cookie Issues

#### Cookie Expired
```
WARNING upload_service [-]: Cookie older than 12h (63.3h) - high risk of session expiry
ERROR upload_service [-]: Upload failed: sessionid cookie expired
```

**Solution:**
```bash
# Option 1: QR Login (recommended)
python scripts/qr_login.py <username> --uploader-dir /path/to/TiktokAutoUploader

# Option 2: Import from browser
python scripts/import_cookies.py <username> /path/to/cookies.json

# Verify
python -m scripts.operator_cli cookie-status
```

#### Cookie File Missing
```
WARNING upload_service [-]: No cookie files found - upload will likely fail
```

**Solution:**
```bash
# Check cookie directory
ls -la TiktokAutoUploader/CookiesDir/

# Should contain: tiktok_session-<username>.cookie
# If missing, run QR login or import cookies
```

#### Cookie Permission Issues
```
PermissionError: [Errno 13] Permission denied: 'CookiesDir/tiktok_session-...'
```

**Solution:**
```bash
# Fix permissions
chmod 700 TiktokAutoUploader/CookiesDir/
chmod 600 TiktokAutoUploader/CookiesDir/*.cookie
```

### 4. Upload Failures

#### Upload Returns False
```
ERROR upload_service [-]: Upload failed after retries: Upload returned False
```

**Diagnosis:**
```bash
# Check recent uploads
python -m scripts.operator_cli list-jobs --status FAILED

# Check specific job
python -m scripts.operator_cli inspect <job_id>
```

**Common Causes:**
| Cause | Solution |
|-------|----------|
| TikTok API changed | Check TiktokAutoUploader updates |
| Video format invalid | Check encoding settings (CRF ≤ 25) |
| Caption violates policy | Check compliance logs |
| Account banned | Check TikTok account status |

#### Duplicate Upload Detected
```
INFO upload_service [-]: Video X already uploaded successfully (job N), skipping
```

**Note:** This is normal idempotency behavior. No action needed.

### 4. Database Issues

#### Database Locked
```
sqlite3.OperationalError: database is locked
```

**Solution:**
```bash
# Ensure only one instance running
systemctl status tiktok-machine

# If stuck, kill and restart
sudo systemctl stop tiktok-machine
# Wait for processes to die
pkill -f orchestrator.py
systemctl start tiktok-machine
```

#### Database Corrupted
```
sqlite3.DatabaseError: database disk image is malformed
```

**Solution:**
```bash
# Stop service
systemctl stop tiktok-machine

# Restore from backup
cp logs/backups/tiktok_20260101_120000.db logs/tiktok.db

# Verify integrity
sqlite3 logs/tiktok.db "PRAGMA integrity_check;"

# Restart
systemctl start tiktok-machine
```

#### Migration Fails
```
sqlite3.OperationalError: duplicate column name: video_hash
```

**Solution:**
```bash
# Check current schema version
sqlite3 logs/tiktok.db "SELECT * FROM schema_version;"

# If stuck, manually run migration or restore backup
```

### 5. Proxy/Network Issues

#### DNS Resolution Fails
```
requests.exceptions.ConnectionError: Failed to resolve 'ip-api.com'
```

**Solution:**
```bash
# Check DNS
nslookup ip-api.com
dig ipinfo.io

# Check /etc/resolv.conf
cat /etc/resolv.conf

# Try different DNS
echo "nameserver 8.8.8.8" | sudo tee /etc/resolv.conf
```

#### SSL Certificate Errors
```
requests.exceptions.SSLError: SSL certificate verify failed
```

**Solution:**
```bash
# Update CA certificates
sudo apt-get update && sudo apt-get install -y ca-certificates
# Or update Python certifi
pip install --upgrade certifi
```

### 6. Video Processing Issues

#### FFmpeg Not Found
```
FileNotFoundError: [Errno 2] No such file or directory: 'ffmpeg'
```

**Solution:**
```bash
# Install ffmpeg
sudo apt-get install ffmpeg  # Ubuntu/Debian
sudo dnf install ffmpeg       # CentOS/RHEL

# Verify
which ffmpeg
ffmpeg -version
```

#### Video Quality Too Low
```
WARNING video_service [-]: QUALITY REGRESSION: 0.15 MB/s below 0.30 floor
```

**Solution:**
```yaml
# Adjust encoding settings in config.yaml
encoding:
  crf: 23          # Lower = better quality (18-28)
  maxrate: "5M"    # Increase for better quality
  bufsize: "8M"    # Buffer size
  preset: "veryfast"  # Slower = better compression
```

#### Video is Static Image
```
ERROR video_service [-]: BROKEN BURN: video has 1 frame(s) (2.00s) - STATIC IMAGE
```

**Cause:** Input video has too few frames.
**Solution:** Check source video duration and frame rate.

### 7. Compliance Failures

#### Caption Rejected
```
WARNING compliance [-]: Caption rejected: banned keyword 'guaranteed' found
```

**Solution:**
- Review banned phrases in `config.yaml` → `compliance.banned_phrases`
- Check `scripts/caption_policy.py` for built-in rules
- Use AI auto-fix: `compliance.use_ai: true`

### 8. Google Drive Sync Issues

#### Sync Fails
```
WARNING orchestrator [-]: Google Drive sync failed. Skipping this cycle.
```

**Diagnosis:**
```bash
# Test rclone
rclone lsd gdrive:
rclone ls gdrive:TikTokContent

# Check config
rclone config show gdrive
```

**Common Causes:**
| Cause | Solution |
|-------|----------|
| rclone not configured | Run `rclone config` |
| Wrong remote name | Check `google_drive.rclone_remote` in config |
| Quota exceeded | Check Google Drive quota |
| Permissions | Verify service account permissions |

### 8. Apify Scraping Issues

#### Apify Token Invalid
```
WARNING competitor_scraper [-]: Apify API token not configured — scraper will be no-op
```

**Solution:**
```bash
# Set APIFY_TOKEN in .env
echo "APIFY_TOKEN=apify_api_..." >> .env
source .env
```

#### No Competitor Data
```
INFO competitor_scraper [-]: Scrape complete: {'error': 'Apify token not configured'}
```

**Solution:**
- Verify APIFY_TOKEN is valid
- Check actor_id is `clockworks/tiktok-scraper`
- Verify competitor handles in config

### 9. Telegram Bot Issues

#### Bot Not Responding
```bash
# Test bot token
curl "https://api.telegram.org/bot<TOKEN>/getMe"

# Check webhook (if used)
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

**Common Issues:**
- Token invalid → Regenerate via @BotFather
- Chat ID wrong → Get chat ID from @userinfobot
- Bot blocked → User must unblock bot

## Log Analysis

### Search Patterns
```bash
# Find all errors
grep -i "error" logs/tiktok.log

# Find warnings
grep -i "warning" logs/tiktok.log

# Track specific job
grep "job_123" logs/tiktok.log

# Monitor real-time
tail -f logs/tiktok.log | grep -E "(ERROR|WARNING|CRITICAL)"
```

### Log Levels
| Level | Meaning |
|-------|---------|
| DEBUG | Detailed diagnostic info |
| INFO | Normal operation events |
| WARNING | Potential issues, non-fatal |
| ERROR | Operation failed, may retry |
| CRITICAL | System failure, manual intervention needed |

## Performance Tuning

### Slow Uploads
- Check proxy latency: `curl -w "@curl-format.txt" -o /dev/null -s -x $TIKTOK_PROXY https://httpbin.org/ip`
- Reduce video quality: increase CRF
- Use faster preset: `preset: "ultrafast"`

### High Memory Usage
- Limit concurrent uploads (currently 1)
- Restart service periodically: `systemctl reload tiktok-machine`
- Monitor: `watch -n 5 'ps aux | grep orchestrator'`

### Database Performance
```bash
# Analyze database
sqlite3 logs/tiktok.db "ANALYZE;"

# Check index usage
sqlite3 logs/tiktok.db "EXPLAIN QUERY PLAN SELECT * FROM posts WHERE video_hash='abc';"

# Vacuum periodically
sqlite3 logs/tiktok.db "VACUUM;"
```

## Getting Help

### Collect Debug Info
```bash
# Create debug bundle
tar -czf debug_$(date +%Y%m%d).tar.gz \
    config/config.yaml \
    logs/tiktok.log \
    logs/tiktok.db \
    .env
```

### Report Issues
Include:
1. Error message and stack trace
2. Config (with secrets redacted)
3. Relevant log excerpts
4. Steps to reproduce
5. Environment: OS, Python version, hardware

### Useful Commands Reference
```bash
# Full system status
python -m scripts.operator_cli summary

# Database integrity
sqlite3 logs/tiktok.db "PRAGMA integrity_check;"

# Backup validation
python -m scripts.operator_cli backup-validate logs/backups/latest.db

# Cookie inspection
python -c "
import pickle
with open('TiktokAutoUploader/CookiesDir/tiktok_session-*.cookie', 'rb') as f:
    cookies = pickle.load(f)
    for c in cookies:
        print(f'{c[\"name\"]}: {c[\"value\"][:20]}...')
"
```