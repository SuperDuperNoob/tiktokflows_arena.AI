# TikTok Auto-Posting Machine — Dependency Graph (Phase 7)

*Generated after Phase 7: Domain Architecture Refinement & Infrastructure Separation.*

---

## Legend

- ███ = **Service** (services/core/)
- ███ = **Repository** (services/repositories/)
- ███ = **Adapter** (services/infrastructure/)
- ███ = **Model** (services/models/)
- ███ = **Utility** (services/utils/)
- ███ = **Script/Entry Point** (scripts/)
- ███ = **External System**
- ███ = **Protected Subsystem** (TiktokAutoUploader/)

---

## Clean Dependency Direction

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  COMPOSITION ROOT                                                           │
│  scripts/orchestrator.py                                                    │
│  (wires: Config, Database, Repositories, Services, Adapters)               │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ creates & injects
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  DOMAIN SERVICES (services/core/)                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│  VideoService        │  UploadService        │  StorageService              │
│  AnalyticsService    │  SchedulerService     │  ProductService              │
│  ProxyService        │                       │                              │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ uses
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  REPOSITORIES (services/repositories/)                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  UploadRepository   │  ProductRepository   │  CaptionRepository            │
│  AnalyticsRepository│  StockRepository     │  EventRepository              │
│  BaseRepository     │  Database (infra)    │                              │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ uses
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  INFRASTRUCTURE ADAPTERS (services/infrastructure/)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│  TikTokAdapter      │  FFmpegAdapter    │  SkiaAdapter                      │
│  RcloneAdapter      │  TelegramAdapter  │  ProxyAdapter                     │
│  AIAdapter          │  SidecarAdapter   │  Config                           │
│  Database           │                   │                                   │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ calls
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  EXTERNAL SYSTEMS                                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│  TikTok Web API (v2)  │  Google Drive (rclone)  │  Telegram Bot API        │
│  OpenAI API           │  Apify (scraper)      │  ip-api.com / ipinfo.io    │
└─────────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PROTECTED SUBSYSTEM (TiktokAutoUploader/)                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  tiktok_uploader.tiktok_v2.upload_video()  ← Called via TikTokAdapter       │
│  (Never modified — treated as upstream dependency)                           │
└─────────────────────────────────────────────────────────────────────────────┘

```

---

## Detailed Service Dependencies

### VideoService
```
VideoService
├── StockRepository          (stock queries)
├── FFmpegAdapter            (encoding, probing)
├── SkiaAdapter              (text rendering)
├── Config                   (encoding params, paths)
├── paths util               (drive_root, queue_dir, etc.)
├── quality util             (MIN_MB_PER_SEC, MIN_OUTPUT_FRAMES)
├── timezone util            (OWN_HANDLE, RIVAL_HANDLE)
├── db_utils                 (mark_raw_consumed, get_conn, ensure_schema)
├── caption_policy           (compliance check)
├── sidecar_manager          (legacy, for sidecar paths)
└── transform_video          (styles, TextRenderer)
```

### UploadService
```
UploadService
├── SidecarManager           (legacy, for queue)
├── Config                   (proxy, tiktok settings)
├── paths util               (queue_dir, failed_dir, success_log, db_path)
├── timezone util            (OWN_HANDLE)
├── proxy util               (normalize, mask, check_exit, transport_error)
├── db_utils                 (mark_raw_consumed, get_conn, ensure_schema)
├── TikTokAdapter            (upload)
├── SidecarAdapter           (cleanup)
└── env_flag (local)
```

### StorageService
```
StorageService
├── Config                   (google_drive settings)
├── paths util               (drive_root, db_path)
├── stock util               (scan_stock)
├── db_utils                 (consumed_pending_cleanup, mark_drive_cleaned)
├── RcloneAdapter            (sync, delete)
└── Database                 (for pending cleanup)
```

### AnalyticsService
```
AnalyticsService
├── AnalyticsRepository      (metrics queries)
├── db_utils                 (get_conn, ensure_schema)
├── analytics util           (reconcile, build_report)
├── CompetitorScraper        (from scripts, for daily scrape)
└── Config                   (apify settings)
```

### SchedulerService
```
SchedulerService
├── UploadRepository         (last post time)
└── timezone util            (MYT_OFFSET, MYT)
```

### ProductService
```
ProductService
├── ProductRepository        (product catalog)
├── StockRepository          (stock counts)
└── Config                   (products_file path)
```

### ProxyService
```
ProxyService
├── ProxyAdapter             (verify, get_current_proxy)
└── Config                   (proxy settings)
```

---

## Repository Dependencies

### UploadRepository
```
UploadRepository
└── BaseRepository (posts table)
```

### ProductRepository
```
ProductRepository
└── BaseRepository (products.json file via Config)
```

### CaptionRepository
```
CaptionRepository
└── BaseRepository (caption_pool table)
```

### AnalyticsRepository
```
AnalyticsRepository
├── BaseRepository (videos, daily_metrics, competitor_* tables)
└── Config (handles for rival gap)
```

### StockRepository
```
StockRepository
└── BaseRepository (raw_stock table)
```

### EventRepository
```
EventRepository
└── BaseRepository (system_events table)
```

---

## Adapter Dependencies

### TikTokAdapter
```
TikTokAdapter
├── Config
└── tiktok_uploader.tiktok_v2.upload_video (TiktokAutoUploader)
```

### FFmpegAdapter
```
FFmpegAdapter
└── Config (encoding params)
```

### SkiaAdapter
```
SkiaAdapter
└── Config (font paths, rendering)
```

### RcloneAdapter
```
RcloneAdapter
└── Config (rclone remote, paths)
```

### TelegramAdapter
```
TelegramAdapter
└── Config (bot token, chat ID)
```

### ProxyAdapter
```
ProxyAdapter
├── Config (proxy endpoint, geo_check)
├── proxy util (normalize, mask, check_exit, transport_error)
└── requests (ip-api.com, ipinfo.io)
```

### AIAdapter
```
AIAdapter
├── Config (ai section: base_url, api_key, model)
└── requests (OpenAI-compatible API)
```

### SidecarAdapter
```
SidecarAdapter
└── (file I/O only — .json, .pid)
```

### Config
```
Config
├── config.yaml (YAML)
├── os.environ (overrides)
└── pathlib (path resolution)
```

### Database
```
Database
├── sqlite3
└── Schema constants (from scripts/db.py)
```

---

## Scripts (Entry Points) Dependencies

### orchestrator.py (Composition Root)
```
orchestrator.py
├── Config (services.infrastructure.config.Config)
├── Database (services.infrastructure.database.Database)
├── VideoService (db_path)
├── StorageService ()
├── UploadService ()
├── AnalyticsService (db_path)
├── SchedulerService (db_path)
├── ProductService (db_path)
├── ProxyService ()
└── Database (repositories)
```

### telegram_bot.py (Legacy)
```
telegram_bot.py
└── lib (scripts.lib — legacy compat)
```

### webapp/server.py (Legacy)
```
webapp/server.py
└── lib (scripts.lib — legacy compat)
```

---

## Cross-Cutting Utilities

### services/utils/analytics.py (Legacy — contains business logic)
```
analytics.py
├── db_utils (get_conn, ensure_schema)
├── timezone (OWN_HANDLE, human, utcnow, stamp)
├── quality (clamp_telegram, MIN_MB_PER_SEC)
├── paths (db_path, daily_report)
├── stock (scan_stock)
├── queue (queue_count)
├── burn_log (recent_burns, quality_check)
└── argparse, re, sys, datetime, etc.
```

### services/utils/db_utils.py
```
db_utils
├── sqlite3
├── paths (db_path)
└── timezone (utcnow)
```

### services/utils/proxy.py
```
proxy
├── urllib.parse.quote
├── requests (ip-api.com, ipinfo.io)
└── urllib.parse.urlparse
```

---

## Forbidden Dependencies (Verified Clean)

❌ Services importing scripts/ directly (except Composition Root)
❌ Repositories importing Services
❌ Adapters importing Services or Repositories
❌ Models importing anything
❌ Utilities importing Services/Repositories/Adapters
❌ Circular dependencies
❌ Global singleton access from Services (Config/Database injected)

---

## Migration Status

| Legacy Module | New Location | Status |
|---------------|--------------|--------|
| scripts/config.py | services.infrastructure.config | ✅ Migrated |
| scripts/db.py | services.infrastructure.database | ✅ Migrated |
| scripts/lib.py | services.utils.* + services.infrastructure.* | ✅ Re-exported (compat) |
| scripts/video_processor.py | services.core.VideoService | ✅ Migrated (legacy kept) |
| scripts/uploader.py | services.core.UploadService | ✅ Migrated (legacy kept) |
| scripts/sync_drive.py | services.core.StorageService | ✅ Migrated (legacy kept) |
| scripts/sync_out.py | services.core.StorageService | ✅ Migrated (legacy kept) |
| scripts/check_burns.py | services.core.VideoService.quality_gate | ✅ Migrated (legacy kept) |
| scripts/ai_growth.py | services.infrastructure.AIAdapter + AnalyticsService | ✅ Migrated (legacy kept) |
| scripts/competitor_scraper.py | AnalyticsService + CompetitorScraper | ✅ Migrated (legacy kept) |
| scripts/generate_report.py | services.utils.analytics + AnalyticsService | ✅ Migrated (legacy kept) |
| scripts/reconcile_metrics.py | services.utils.analytics + AnalyticsService | ✅ Migrated (legacy kept) |