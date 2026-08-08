# Configuration Audit — Phase 15

**Date:** 2026-08-09
**Branch:** main

---

## 1. Configuration Ownership

### Every Config Key Has an Owner

| Key Path | Owner | Used By |
|----------|-------|---------|
| `tiktok.session_username` | Orchestrator | TikTokAdapter, qr_login, import_cookies |
| `tiktok.uploader_dir` | Orchestrator | TikTokAdapter, qr_login, import_cookies |
| `tiktok.cookie_max_age_days` | Orchestrator | UploadService.check_cookie_expiry |
| `posting.interval_minutes` | SchedulerService | Orchestrator main loop |
| `posting.jitter_minutes` | SchedulerService | Orchestrator main loop |
| `posting.quiet_hours_start` | SchedulerService | Orchestrator main loop |
| `posting.quiet_hours_end` | SchedulerService | Orchestrator main loop |
| `posting.daily_post_target` | SchedulerService | Telegram /status, webapp /api/status |
| `content.raw_dir` | StorageService | VideoService.scan_raw, StorageService.sync_from_drive |
| `content.processed_dir` | VideoService | UploadService.queue_dir, StorageService.sync_to_drive |
| `content.posted_dir` | VideoService | Archive after burn |
| `content.failed_dir` | VideoService, UploadService | Quarantine |
| `content.sounds_dir` | VideoService | Audio track selection |
| `content.preset_text` | VideoService, ai_growth | Caption pool source |
| `content.product_id_file` | VideoService | Product → TikTok Shop ID mapping |
| `proxy.endpoint` | UploadService | Proxy verification, TikTok upload |
| `proxy.strict_mode` | UploadService | Abort on non-MY geo |
| `proxy.geo_check` | UploadService | Pre-upload IP check |
| `proxy.expected_country` | UploadService | Geo verification target |
| `proxy.verify_endpoint` | UploadService | ipinfo.io fallback |
| `proxy.datacenter_keywords` | ProxyAdapter | Datacenter detection |
| `ai.api_key` | AIAdapter | All AI calls |
| `ai.base_url` | AIAdapter | API endpoint |
| `ai.model` | AIAdapter | Model selection |
| `ai.enable_ai` | AIAdapter | Global AI kill switch |
| `ai.caption_per_video` | AIAdapter | Per-video captions (default: false) |
| `ai.max_calls_per_day` | AIAdapter | Daily budget (default: 1) |
| `ai.timeout_seconds` | AIAdapter | Request timeout |
| `ai.retries` | AIAdapter | Retry count |
| `compliance.strict_mode` | ComplianceEngine | Reject on regex hit |
| `compliance.use_ai` | ComplianceEngine | Enable AI layer |
| `compliance.banned_phrases` | ComplianceEngine | Additional banned phrases |
| `encoding.crf` | FFmpegAdapter, VideoService | Video quality |
| `encoding.maxrate` | FFmpegAdapter, VideoService | Peak bitrate |
| `encoding.bufsize` | FFmpegAdapter, VideoService | Buffer size |
| `encoding.abr` | FFmpegAdapter, VideoService | Audio bitrate |
| `encoding.preset` | FFmpegAdapter, VideoService | Encoding speed |
| `encoding.threads` | FFmpegAdapter, VideoService | CPU threads |
| `encoding.min_mb_per_sec` | VideoService.quality_gate | Quality floor |
| `encoding.min_output_frames` | VideoService.quality_gate | Still image guard |
| `encoding.overlay_accent_rate` | VideoService | Red accent probability |
| `rendering.force_style` | VideoService | Override style selection |
| `analytics.rival_handle` | AnalyticsService | Competitor benchmarking |
| `google_drive.rclone_remote` | StorageService | rclone remote name |
| `google_drive.remote_path` | StorageService | Drive folder path |
| `google_drive.products_file` | ProductService | products.json location |
| `apify.token` | AnalyticsService | Competitor scraping |
| `apify.actor_id` | AnalyticsService | Scraper actor |
| `apify.competitors` | AnalyticsService | Handles to scrape |
| `apify.results_per_page` | AnalyticsService | Pagination |
| `apify.max_competitors` | AnalyticsService | Limit |
| `apify.scrape_schedule_hour` | Orchestrator | Daily job timing |
| `telegram.bot_token` | TelegramAdapter, webapp | Bot API auth |
| `telegram.allowed_user_id` | TelegramAdapter, webapp | Authorization |
| `logging.db_path` | Database, all repos | SQLite file |
| `timezone.tz` | timezone util, Orchestrator | Business timezone |

---

## 2. Environment Variable Mapping

| Env Var | Config Key | Override Behavior |
|---------|------------|-------------------|
| `TIKTOK_MACHINE_CONFIG` | (config path) | Sets config file location |
| `TIKTOK_PROXY` | `proxy.endpoint` | Full proxy URL with credentials |
| `AI_API_KEY` | `ai.api_key` | OpenAI-compatible API key |
| `TIKTOKFLOW_TZ` | `timezone.tz` | Business timezone |
| `TIKTOK_SESSION_USER` | `tiktok.session_username` | TikTok cookie profile |
| `TIKTOK_RIVAL_HANDLE` | `analytics.rival_handle` | Competitor handle |
| `TIKTOKFLOW_HOME` / `TIKTOK_MACHINE_HOME` | (project root) | Project root override |

---

## 3. Duplicate Configuration Paths

### Critical Duplicates (Multiple Sources of Truth)

| Parameter | Sources | Risk |
|-----------|---------|------|
| **Proxy endpoint** | `config.yaml:proxy.endpoint`, `TIKTOK_PROXY` env, TiktokAU config.txt | Inconsistent formats, credentials exposure |
| **TikTok session username** | `config.yaml:tiktok.session_username`, `TIKTOK_SESSION_USER` env, `lib.OWN_HANDLE` | Used in 3+ places, divergence possible |
| **Project root** | `TIKTOKFLOW_HOME`, `TIKTOK_MACHINE_HOME`, auto-detect | Complex auto-detect logic |
| **Database path** | `config.yaml:logging.db_path`, `lib.db_path()`, `db.py` constructor | Passed around explicitly |
| **Encoding params** | `config.yaml:encoding.*`, `transform_video.FFMPEG_*` env vars, `lib.cfg()` | Three sources of truth |
| **Quality floors** | `config.yaml:encoding.min_mb_per_sec`, `lib.MIN_MB_PER_SEC`, `transform_video.MIN_MB_PER_SEC` | Three definitions |
| **Timezone** | `config.yaml:timezone.tz`, `TIKTOKFLOW_TZ` env, `lib.TIMEZONE` | Used in lib + orchestrator separately |

### Encoding Parameter Duplication Detail

| Parameter | config.yaml | transform_video.py | video_processor.py | lib.py |
|-----------|-------------|-------------------|-------------------|--------|
| CRF | `encoding.crf: 23` | `FFMPEG_CRF = os.environ.get("FFMPEG_CRF", "23")` | `lib.cfg("encoding","crf",23)` | `cfg("encoding","crf",23)` |
| Maxrate | `encoding.maxrate: "5M"` | `FFMPEG_MAXRATE = os.environ.get("FFMPEG_MAXRATE", "5M")` | `lib.cfg("encoding","maxrate","5M")` | Same |
| Preset | `encoding.preset: "veryfast"` | `FFMPEG_PRESET = os.environ.get("FFMPEG_PRESET", "veryfast")` | `lib.cfg("encoding","preset","veryfast")` | Same |
| Threads | `encoding.threads: 1` | `FFMPEG_THREADS = os.environ.get("FFMPEG_THREADS", "1")` | `lib.cfg("encoding","threads",1)` | Same |
| Min MB/s | `encoding.min_mb_per_sec: 0.30` | `MIN_MB_PER_SEC = 0.30` | `lib.MIN_MB_PER_SEC` | `cfg("encoding","min_mb_per_sec",0.30)` |
| Min frames | `encoding.min_output_frames: 10` | `MIN_OUTPUT_FRAMES = 10` | `lib.MIN_OUTPUT_FRAMES` | `cfg("encoding","min_output_frames",10)` |

---

## 4. Configuration Access Patterns

### Pattern 1: `services.infrastructure.config.get_config()` (Services)
```python
from services.infrastructure.config import get_config
cfg = get_config()
value = cfg.get("proxy", "endpoint")
```

### Pattern 2: `lib.cfg()` (Legacy Scripts)
```python
import lib
value = lib.cfg("encoding", "crf", default=23)
```

### Pattern 3: Direct Config Dict (Orchestrator)
```python
with open(config_path) as f:
    self.config = yaml.safe_load(f)
value = self.config.get("posting", {}).get("interval_minutes", 120)
```

### Pattern 4: Module-Level Constants (transform_video.py)
```python
FFMPEG_CRF = os.environ.get("FFMPEG_CRF", "23")
```

### Pattern 5: Explicit Config Object (compliance.py, ai_growth.py)
```python
def __init__(self, config: dict, ai_config: dict):
    self.strict_mode = config.get("strict_mode", True)
    self.ai_api_key = ai_config.get("api_key", "")
```

---

## 5. Dangerous Hidden Defaults

| Default | Location | Risk |
|---------|----------|------|
| `proxy.endpoint: ""` | Config.DEFAULTS | No proxy = datacenter IP = shadowban |
| `ai.api_key: ""` | Config.DEFAULTS | AI calls silently fail |
| `telegram.bot_token: ""` | Config.DEFAULTS | Bot disabled silently |
| `google_drive.rclone_remote: ""` | Config.DEFAULTS | Drive sync fails silently |
| `apify.token: ""` | Config.DEFAULTS | Scraping fails silently |
| `encoding.crf: 23` | Config.DEFAULTS | Safe default |
| `encoding.min_mb_per_sec: 0.30` | Config.DEFAULTS | Quality floor |
| `proxy.strict_mode: true` | Config.DEFAULTS | Aborts on bad proxy (SAFE) |
| `proxy.geo_check: true` | Config.DEFAULTS | Pre-upload check (SAFE) |

---

## 6. Missing Configuration (Hardcoded Values)

| Hardcoded Value | Location | Should Be Config Key |
|-----------------|----------|---------------------|
| `/tmp/tiktok-machine-upload.lock` | `scripts/uploader.py:154` | `content.lock_dir` |
| `/dev/shm` for temp PNG | `scripts/video_processor.py:476` | `content.temp_dir` |
| `/tmp/tiktok_qr_*.png` | `scripts/qr_login.py` | `content.temp_dir` |
| rclone exclude patterns | `scripts/sync_drive.py` | `google_drive.exclude_patterns` |
| `max_retries = 2` | `scripts/uploader.py` | `upload.max_retries` |
| Retry backoff 30s/60s | `scripts/uploader.py` | `upload.retry_backoff` |
| Anti-bot jitter 5-90s | `scripts/uploader.py` | `upload.jitter_range` |
| Sidecar cleanup on success | `scripts/uploader.py` | `upload.cleanup_on_success` |
| Burn log retention | Unlimited | `logging.burn_log_retention_days` |
| System events retention | Unlimited | `logging.events_retention_days` |

---

## 7. Secrets Management

| Secret | Location | Masked in API? | Rotation |
|--------|----------|----------------|----------|
| Telegram bot token | `config.yaml:telegram.bot_token` | ✅ webapp/server.py | Manual |
| Proxy endpoint (with creds) | `config.yaml:proxy.endpoint` | ✅ webapp/server.py, lib.mask_proxy() | Manual |
| AI API key | `config.yaml:ai.api_key` | ✅ webapp/server.py | Manual |
| Apify token | `config.yaml:apify.token` | ✅ webapp/server.py | Manual |
| TikTok cookies | `TiktokAutoUploader/CookiesDir/*.cookie` | File-based | Manual (14 days) |

**Issues:**
1. No secret rotation mechanism
2. Proxy credentials in URL (logged masked but in memory)
3. No encryption at rest (plain text YAML)
4. File permissions only protection

---

## 8. Validation Status

### Current Validation (services.infrastructure.config.Config)

**Required Keys (fail fast unless TESTING=1):**
- `telegram.bot_token`, `telegram.allowed_user_id`
- `proxy.endpoint`
- `ai.base_url`, `ai.api_key`
- `tiktok.session_username`, `tiktok.uploader_dir`

**Additional Validation:**
- Proxy URL format
- AI API key required when `enable_ai: true`
- CRF 0-51
- Positive posting interval
- Valid timezone

**Missing Validation:**
- rclone remote exists
- Cookie directory writable
- Sounds directory has MP3s
- Proxy endpoint reachable
- AI API reachable

---

## 9. Recommendations

### Immediate
1. **Deprecate `scripts.lib.cfg()`** - Migrate all legacy scripts to `services.infrastructure.config.get_config()`
2. **Remove module-level constants** in `transform_video.py` - Use `cfg()` everywhere
3. **Add missing config keys** for hardcoded paths (lock_dir, temp_dir, retry settings)

### Short-term
1. **Split secrets** - Move to `.env` file (python-dotenv already in requirements)
2. **Add config versioning** - Schema version for migrations
3. **Environment-specific configs** - `config.prod.yaml`, `config.dev.yaml`

### Long-term
1. **Typed config with Pydantic** - Validation, defaults, documentation in one place
2. **Secret manager integration** - HashiCorp Vault, AWS Secrets Manager
3. **Config API versioning** - Prevent breaking changes

---

## 10. Configuration Completeness Check

| Category | Coverage |
|----------|----------|
| TikTok account | ✅ Complete |
| Posting schedule | ✅ Complete |
| Content paths | ✅ Complete |
| Proxy | ✅ Complete |
| AI | ✅ Complete |
| Compliance | ✅ Complete |
| Encoding quality | ✅ Complete |
| Rendering | ✅ Complete |
| Analytics | ✅ Complete |
| Google Drive | ✅ Complete |
| Apify scraping | ✅ Complete |
| Telegram | ✅ Complete |
| Logging/Database | ✅ Complete |
| Timezone | ✅ Complete |
| **Hardcoded operational params** | ❌ **Incomplete** (lock dir, temp dir, retry settings) |