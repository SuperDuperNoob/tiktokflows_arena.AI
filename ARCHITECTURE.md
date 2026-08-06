# TikTok Auto-Posting Machine — Real Architecture (Phase 7)

*Updated after Phase 7: Domain Architecture Refinement & Infrastructure Separation. This document reflects the actual implementation.*

---

## System Overview

This is a **service-oriented architecture** built around **TiktokAutoUploader** (the protected upload engine). The orchestrator coordinates all pipeline stages through dependency-injected services.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        EXTERNAL INTERFACES                                   │
├─────────────────────┬───────────────────────────┬───────────────────────────┤
│   Telegram Bot      │    Web Dashboard          │   CLI / Cron Jobs         │
│   (python-telegram- │   (FastAPI + Static       │   (Direct script runs)    │
│    bot, polling)    │    HTML/CSS/JS)           │                           │
└──────────┬──────────┴──────────────┬───────────┴──────────────┬────────────┘
           │                         │                          │
           ▼                         ▼                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      COMPOSITION ROOT (scripts/orchestrator.py)              │
├─────────────────────────────────────────────────────────────────────────────┤
│  Single entry point that wires:                                             │
│  - Configuration (services.infrastructure.config.Config)                   │
│  - Database (services.infrastructure.database.Database)                    │
│  - Repositories (services.repositories.*)                                  │
│  - Services (services.core.*)                                              │
│  - Infrastructure Adapters (services.infrastructure.*)                     │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      DOMAIN SERVICES (services/core/)                        │
├──────────────┬──────────────┬──────────────┬──────────────┬────────────────┤
│ VideoService │ UploadService│ StorageService│AnalyticsService│SchedulerService│
│ ProductService│ProxyService  │               │                │               │
│  - Process   │  - Queue     │  - rclone     │  - Scrape      │  - Timing    │
│  - Caption   │  - Proxy     │  - sync       │  - Reconcile   │  - Quiet hrs │
│  - Quality   │  - Retry     │  - cleanup    │  - Report      │              │
└──────────────┴──────────────┴──────────────┴──────────────┴────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      REPOSITORIES (services/repositories/)                   │
├──────────────┬──────────────┬──────────────┬──────────────┬────────────────┤
│ UploadRepo   │ ProductRepo  │ CaptionRepo  │ AnalyticsRepo│ StockRepo      │
│ EventRepo    │              │              │              │                │
│  - CRUD      │  - JSON sync │  - Pool mgmt │  - Metrics   │  - Ledger     │
└──────────────┴──────────────┴──────────────┴──────────────┴────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      INFRASTRUCTURE ADAPTERS (services/infrastructure/)      │
├──────────────┬──────────────┬──────────────┬──────────────┬────────────────┤
│ TikTokAdapter│ FFmpegAdapter│ SkiaAdapter  │ RcloneAdapter│ TelegramAdapter│
│ ProxyAdapter │ AIAdapter    │ Config       │ Database     │ SidecarAdapter │
│  - Upload    │  - Encode    │  - Render    │  - sync      │  - Bot API     │
│  - Verify    │  - Probe     │  - Emoji     │  - cleanup   │  - JSON/.pid   │
└──────────────┴──────────────┴──────────────┴──────────────┴────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      EXTERNAL SYSTEMS                                        │
├──────────────┬──────────────┬──────────────┬──────────────┬────────────────┤
│ TikTok Web   │ Google Drive │ Telegram Bot │ OpenAI API   │ Apify Scraper  │
│ API (v2)     │ (rclone)     │ API          │ (captions)   │ (competitor)   │
│ ip-api.com   │ ipinfo.io    │              │              │                │
└──────────────┴──────────────┴──────────────┴──────────────┴────────────────┘
```

**Protected Subsystem**: `TiktokAutoUploader/` (never modified, treated as upstream dependency)

---

## Component Responsibilities

### 1. Composition Root

| Component | Location | Responsibility |
|-----------|----------|----------------|
| Orchestrator | `scripts/orchestrator.py` | Wires config, DB, repositories, services, adapters; runs main loop |

### 2. Domain Services (services/core/)

| Service | Responsibility |
|---------|----------------|
| VideoService | Video processing, caption generation, quality gate, stock selection |
| UploadService | Queue processing, proxy verification, retry logic, TikTok upload |
| StorageService | Google Drive sync (pull/push), raw video cleanup |
| AnalyticsService | Competitor scraping, metrics reconciliation, report generation |
| SchedulerService | Post timing, quiet hours, jitter |
| ProductService | Product catalog (JSON + DB) |
| ProxyService | Proxy health, geo-verification |

### 3. Repositories (services/repositories/)

| Repository | Table(s) | Responsibility |
|------------|----------|----------------|
| UploadRepository | `posts` | Upload job CRUD |
| ProductRepository | `products.json` | Product catalog |
| CaptionRepository | `caption_pool` | Caption pool management |
| AnalyticsRepository | `videos`, `daily_metrics`, `competitor_*` | Metrics queries |
| StockRepository | `raw_stock` | Raw video ledger |
| EventRepository | `system_events` | Audit logging |

### 4. Infrastructure Adapters (services/infrastructure/)

| Adapter | External System | Responsibility |
|---------|-----------------|----------------|
| TikTokAdapter | TikTok Web API (v2) | Video upload with product anchors |
| FFmpegAdapter | FFmpeg | Encoding, probing |
| SkiaAdapter | Skia | Text rendering with emoji |
| RcloneAdapter | Google Drive (rclone) | Sync, delete |
| TelegramAdapter | Telegram Bot API | Notifications |
| ProxyAdapter | ip-api.com, ipinfo.io | Geo-verification |
| AIAdapter | OpenAI-compatible API | Captions, compliance, strategy |
| Config | config.yaml | Centralized configuration |
| Database | SQLite | Connection, schema, migrations |

### 5. Domain Models (services/models/)

UploadJob, VideoAsset, Product, Caption, ComplianceResult, UploadResult, GrowthReport, DailySummary, ProxyStatus, ProxyType

---

## Data Flow

```
Google Drive (rclone remote: gdrive:TikTokContent)
       │
       ▼ StorageService.sync_from_drive() (rclone copy --exclude processed/failed/posted)
content/raw/<Product>/raw_001.mp4
       │
       ▼ VideoService.scan_raw() + StockRepository (excludes posted_at)
       ▼ VideoService.quality_gate() (ffprobe scan queue, quarantine 1-frame burns)
       ▼ VideoService.process_one()
           ├─ Pick product (weighted: stock * performance, penalize recent)
           ├─ Pick raw video (random from least-used)
           ├─ Generate caption (preset pool + hooks/CTAs/emojis + policy gate)
           ├─ Render overlay PNG (SkiaAdapter, 8 styles, emoji support)
           ├─ FFmpegAdapter.encode (CRF 23, maxrate 5M, eof_action=repeat)
           ├─ Quality check (frames ≥ 10, MB/s ≥ floor)
           ├─ Archive raw → content/processed/<Product>/
           ├─ DB: StockRepository.mark_consumed() → raw_stock.posted_at = now (SOURCE OF TRUTH)
           └─ SidecarAdapter.write() → content/processed/queue/
       │
       ▼ UploadService.process_upload_queue()
           ├─ Find newest mp4 with sidecar
           ├─ ProxyAdapter.verify() (ip-api.com → ipinfo.io)
           ├─ Strict mode: abort if non-MY or datacenter
           ├─ Anti-bot jitter (5-90s)
           ├─ TikTokAdapter.upload_video() with proxy + product anchors
           ├─ Retry on TikTok API failure (2x, backoff)
           ├─ NO retry on proxy transport error (protects metered GB)
           ├─ On success: log analytics, cleanup sidecars + mp4, success.log
           └─ On fail: move to failed/ with reason.txt, failed.log
       │
       ▼ StorageService.sync_to_drive() (after success)
           ├─ rclone copy logs + processed/ → GDrive
           ├─ DB: StockRepository.consumed_pending_cleanup()
           ├─ rclone deletefile each from GDrive
           └─ DB: StockRepository.mark_drive_cleaned()
       │
       ▼ Daily Jobs (3 AM MYT)
           ├─ AnalyticsService: CompetitorScraper → competitor_videos, competitor_daily
           ├─ AnalyticsService: reconcile() → match videos.tiktok_video_id via caption/time
           ├─ AnalyticsService: build() → daily_report.txt (stock, posted, performance)
           └─ (if /growth triggered) AIAdapter → growth_report.txt + preset_text.txt
```

---

## Configuration Architecture

**Single source**: `config/config.yaml` (git-ignored, holds secrets)

**Loading**: `services.infrastructure.config.Config` (singleton with thread-safe reload)

**Layers**:
1. `config.yaml` (primary)
2. Environment variables (override specific: `TIKTOKFLOW_HOME`, `TIKTOK_MACHINE_CONFIG`, `TIKTOKFLOW_TZ`, `TIKTOK_SESSION_USER`, `TIKTOK_RIVAL_HANDLE`, `TIKTOK_PROXY`, `AI_API_KEY`)
3. Hardcoded defaults in `Config.DEFAULTS`

**Validation**: Required keys checked on load (unless `TESTING=1`)

---

## Database Architecture

**Single SQLite file**: `logs/tiktok.db` (WAL mode, foreign_keys=ON)

**Operational Tables** (from `Database._init_schema`):
- `posts` — Upload records (PENDING→TRANSFORMING→POSTED/FAILED)
- `raw_stock` — **Ledger**: every raw video, `posted_at` = consumed (source of truth)
- `caption_pool` — Approved captions per product (compliance_checked flag)
- `competitor_data` — Legacy dashboard table (from Apify)
- `system_events` — Audit log (UPLOAD_SUCCESS, PROXY_FAIL, etc.)

**Analytics Tables** (from `ensure_schema`):
- `videos` — Local upload log (invented video_id)
- `daily_metrics` — Scraped metrics per video per day
- `competitor_videos` — Per-video scraped data (handle, views, sound, hashtags)
- `competitor_daily` — Per-handle daily aggregates
- `daily_summary` — AI growth cache (ai_called_at = daily budget gate)

**Key Design**: `raw_stock.posted_at` is the **single source of truth** for "already posted". Drive deletion is cosmetic cleanup only.

---

## Concurrency Model

| Component | Concurrency |
|-----------|-------------|
| Orchestrator | Single-threaded loop (systemd restarts on crash) |
| Telegram bot | Background thread (asyncio event loop) |
| Web API | FastAPI + uvicorn (multi-worker capable) |
| SQLite | WAL mode → concurrent reads, serialized writes |
| rclone | Single transfer (`--transfers 1`) |
| TiktokAU | Single upload at a time (flock lock in uploader.py) |
| AI calls | Sequential, cached (1/day) |

**No**: Message queues, worker pools, or distributed coordination.

---

## External Dependencies

| Service | Purpose | Auth | Called By |
|---------|---------|------|-----------|
| TikTok Web API | Video upload | Session cookies | `TikTokAdapter` |
| Google Drive | Content storage | rclone OAuth token | `RcloneAdapter` |
| Telegram Bot API | Notifications + control | Bot token | `TelegramAdapter` |
| OpenAI-compatible API | Captions, compliance, strategy | API key | `AIAdapter` |
| Apify (clockworks/tiktok-scraper) | Competitor scraping | API token | `AnalyticsService` |
| ip-api.com / ipinfo.io | Proxy geo verification | None (free tier) | `ProxyAdapter` |
| Cloudflare Tunnel | Web access (no open ports) | Tunnel token | `cloudflared.service` |

---

## File System Layout

```
/opt/tiktok-machine/ (PROJECT_ROOT)
├── config/
│   └── config.yaml                 # Master config (secrets, not in git)
├── content/
│   ├── raw/                        # Synced from GDrive (source videos)
│   │   ├── <Product>/              # One folder per product
│   │   ├── preset_text.txt         # Caption pool (--- separated)
│   │   └── product_id.txt          # Product → TikTok Shop ID + titles/captions
│   ├── processed/                  # Rendered videos + sidecars (upload queue)
│   ├── posted/                     # Archived after successful upload
│   └── failed/                     # Quarantined burns / failed uploads
├── sounds/                         # Royalty-free MP3 tracks
├── logs/
│   ├── tiktok.db                   # SQLite database
│   ├── burn_log.jsonl              # VideoProcessor audit trail
│   ├── deleted.log                 # Audit: raw files archived
│   ├── success.log                 # Successful uploads
│   ├── failed.log                  # Failed uploads
│   ├── growth_report.txt           # AI growth output
│   ├── daily_report.txt            # OPS report
│   └── drive_cleanup.log           # sync_out audit
├── scripts/                        # Entry points (orchestrator, telegram_bot, etc.)
├── services/                       # Domain layer (core, repositories, infrastructure, models, utils)
├── webapp/                         # FastAPI dashboard
├── deploy/                         # systemd services, setup.sh
├── docs/                           # Guides
├── TiktokAutoUploader/             # **Protected** upload engine (upstream dependency)
│   ├── tiktok_uploader/
│   ├── api/                        # FastAPI (unused by orchestrator)
│   └── scheduler/                  # APScheduler (unused)
└── venv/                           # Python virtualenv
```

---

## Security Model

- All services run as `tiktok` system user (non-root)
- Telegram bot only responds to `allowed_user_id`
- Web interface behind Cloudflare Tunnel (no open ports)
- Secrets in `config.yaml` (git-ignored), masked in API responses
- Proxy used **only for upload traffic**; AI/Telegram/Apify use direct VPS IP
- SQLite WAL mode for concurrent read safety
- Failed burns quarantined, never uploaded
- Raw videos never deleted, only archived
- Cookie files stored locally, only sent to TikTok API

---

## Dependency Direction (Clean)

```
Composition Root (orchestrator.py)
         │
         ▼
Domain Services (services/core/)
         │
         ▼
Repositories (services/repositories/)
         │
         ▼
Infrastructure Adapters (services/infrastructure/)
         │
         ▼
External Systems (TikTok, Google Drive, Telegram, etc.)

Scripts (entry points) → Composition Root → Services → Repositories/Adapters
```

**No reverse dependencies. No cycles. No hidden globals.** Configuration and database are injected through the composition root.

---

## Remaining Technical Debt (Post-Phase 7)

1. **scripts/lib.py** — Still exists for backward compatibility with unmigrated scripts/tests. Contains ~250 lines of re-exports.
2. **analytics.py utility** — Contains business logic (reconcile, report generation) that duplicates AnalyticsService. Should be removed once scripts are migrated.
3. **webapp/server.py** — Still imports `scripts.lib` directly. Should be migrated to use services.
4. **Telegram bot** — Still in `scripts/telegram_bot.py`, uses `scripts.lib`. Should become a service.
4. **Sidecar format** — Dual `.json` + legacy `.pid` format for backward compatibility.
5. **Competitor data duplication** — `competitor_data` table (legacy) vs `competitor_videos`/`competitor_daily` (analytics).
6. **AIAdapter in analytics.py** — `check_compliance` uses AI but compliance is regex-first in `compliance.py`.

---

## Phase 7 Summary

**Completed:**
- ✅ Domain Audit — All domains have clear ownership
- ✅ Infrastructure Separation — `config.py` → `services.infrastructure.config`, `db.py` → `services.infrastructure.database`
- ✅ Composition Root — `scripts/orchestrator.py` is the single wiring point
- ✅ Utility Audit — Business logic identified in `analytics.py` utility (documented for future migration)
- ✅ Repository Audit — All repositories only own persistence
- ✅ Adapter Audit — All adapters only communicate with external systems
- ✅ Domain Boundaries — Each capability is self-contained in its service
- ✅ Dependency Direction — Clean, no cycles, no hidden globals
- ✅ Technical Debt Audit — Documented above
- ✅ Naming Audit — Consistent naming: `*_service.py`, `*_repository.py`, `*_adapter.py`, `*_model.py`, `*_util.py`
- ✅ Documentation — This file updated, other docs to follow
- ✅ Tests — All 56 tests pass
- ✅ Orchestrator — Starts and runs correctly