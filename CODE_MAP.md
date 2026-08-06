# TikTok Auto-Posting Machine — Code Map (Phase 7)

*Complete inventory of every Python module in the repository. Updated after Phase 7: Domain Architecture Refinement & Infrastructure Separation.*

---

## Services Directory (`/services/`)

### Core Services (`/services/core/`)

| File | Lines | Type | Status | Description |
|------|-------|------|--------|-------------|
| `analytics_service.py` | 78 | Service | **PRODUCTION** | Daily jobs (scrape, reconcile, report), dashboard data, growth reports, metrics reconciliation |
| `proxy_service.py` | 51 | Service | **PRODUCTION** | Proxy health, geo-verification, current proxy retrieval via ProxyAdapter |
| `scheduler_service.py` | 71 | Service | **PRODUCTION** | Post timing, quiet hours (2-6 MYT), jitter (±30min), interval (120min) |
| `storage_service.py` | 126 | Service | **PRODUCTION** | Google Drive sync (pull raw, push logs/processed, delete posted raws via rclone) |
| `upload_service.py` | 300 | Service | **PRODUCTION** | Queue processing, proxy verification, retry logic, TikTok upload, sidecar cleanup |
| `video_service.py` | 672 | Service | **PRODUCTION** | Video processing, caption generation, quality gate, stock selection, FFmpeg/Skia integration |
| `product_service.py` | 89 | Service | **PRODUCTION** | Product catalog (JSON + DB sync), stock levels |

### Infrastructure Adapters (`/services/infrastructure/`)

| File | Lines | Type | Status | Description |
|------|-------|------|--------|-------------|
| `ai_adapter.py` | 116 | Adapter | **PRODUCTION** | OpenAI-compatible API for captions, compliance, strategy. Cached (1 call/day). |
| `config.py` | 346 | Infrastructure | **PRODUCTION** | Centralized config (YAML + env), validation, singleton, reload. Replaces `scripts/config.py`. |
| `database.py` | 448 | Infrastructure | **PRODUCTION** | SQLite wrapper, schema, migrations. Replaces `scripts/db.py`. |
| `ffmpeg_adapter.py` | 100 | Adapter | **PRODUCTION** | FFmpeg encoding, probing (resolution, duration, frames). |
| `proxy_adapter.py` | 73 | Adapter | **PRODUCTION** | Proxy geo-verification (ip-api.com → ipinfo.io), normalization, masking. |
| `rclone_adapter.py` | 85 | Adapter | **PRODUCTION** | Google Drive sync via rclone (pull raw, push logs/processed, delete posted). |
| `sidecar_adapter.py` | 78 | Adapter | **PRODUCTION** | Read/write/cleanup .json + .pid sidecars for upload queue. |
| `skia_adapter.py` | 150 | Adapter | **PRODUCTION** | Text rendering with emoji (Skia primary). 8 styles, random fonts/sizes. |
| `telegram_adapter.py` | 37 | Adapter | **PRODUCTION** | Telegram Bot API notifications (stubbed, logged). |
| `tiktok_adapter.py` | 45 | Adapter | **PRODUCTION** | TikTok Web API v2 upload with product anchors. |
| `__init__.py` | 6 | Package | **PRODUCTION** | Package exports. |

### Domain Models (`/services/models/`)

| File | Lines | Type | Status | Description |
|------|-------|------|--------|-------------|
| `upload_job.py` | ~80 | Model | **PRODUCTION** | UploadJob, UploadJobStatus enum |
| `video_asset.py` | ~60 | Model | **PRODUCTION** | VideoAsset, VideoQuality enum |
| `product.py` | ~70 | Model | **PRODUCTION** | Product |
| `caption.py` | ~80 | Model | **PRODUCTION** | Caption, CaptionSource enum |
| `compliance_result.py` | ~50 | Model | **PRODUCTION** | ComplianceResult |
| `upload_result.py` | ~60 | Model | **PRODUCTION** | UploadResult |
| `growth_report.py` | ~70 | Model | **PRODUCTION** | GrowthReport |
| `daily_summary.py` | ~70 | Model | **PRODUCTION** | DailySummary |
| `proxy_status.py` | 49 | Model | **PRODUCTION** | ProxyStatus, ProxyType enum |
| `__init__.py` | 25 | Package | **PRODUCTION** | Exports all models including ProxyType |

### Repositories (`/services/repositories/`)

| File | Lines | Type | Status | Description |
|------|-------|------|--------|-------------|
| `analytics_repository.py` | 150 | Repository | **PRODUCTION** | Metrics queries (recent posts, performance, views delta, rival gap) |
| `base.py` | 77 | Base | **PRODUCTION** | BaseRepository with connection pooling, CRUD helpers |
| `caption_repository.py` | 94 | Repository | **PRODUCTION** | Caption pool CRUD, compliance filtering |
| `event_repository.py` | 39 | Repository | **PRODUCTION** | System events logging |
| `product_repository.py` | 84 | Repository | **PRODUCTION** | Product catalog (JSON file sync) |
| `stock_repository.py` | 68 | Repository | **PRODUCTION** | Raw video ledger (sync, counts, mark consumed/used) |
| `upload_repository.py` | 103 | Repository | **PRODUCTION** | Upload job CRUD, status updates, queries |
| `__init__.py` | 21 | Package | **PRODUCTION** | Exports all repositories + Database from infrastructure |

### Utilities (`/services/utils/`)

| File | Lines | Type | Status | Description |
|------|-------|------|--------|-------------|
| `analytics.py` | 383 | Utility | **LEGACY** | Contains business logic (reconcile, report) — duplicates AnalyticsService. Documented for migration. |
| `burn_log.py` | ~60 | Utility | **PRODUCTION** | Burn log analysis (recent burns, quality check) |
| `db_utils.py` | 176 | Utility | **PRODUCTION** | DB connection, schema, raw_stock ledger helpers |
| `paths.py` | ~60 | Utility | **PRODUCTION** | Path resolution (content dirs, queue, logs, DB, etc.) |
| `proxy.py` | 127 | Utility | **PRODUCTION** | Proxy URL normalization, masking, geo-check, transport error detection |
| `quality.py` | ~30 | Utility | **PRODUCTION** | Quality constants (MIN_MB_PER_SEC, MIN_OUTPUT_FRAMES) |
| `queue.py` | ~30 | Utility | **PRODUCTION** | Queue counting |
| `stock.py` | ~30 | Utility | **PRODUCTION** | Stock scanning |
| `timezone.py` | ~50 | Utility | **PRODUCTION** | MYT timezone (UTC+8), handles, timestamps |
| `__init__.py` | ~20 | Package | **PRODUCTION** | Exports all utilities |

---

## Scripts Directory (`/scripts/`) — Entry Points

### Primary Entry Points

| File | Lines | Type | Status | Description |
|------|-------|------|--------|-------------|
| `orchestrator.py` | 231 | **Composition Root** | **PRODUCTION** | Wires config, DB, repositories, services, adapters; runs main loop (2h ±30min). |
| `telegram_bot.py` | 585 | Background service | **LEGACY** | Telegram bot interface (polling thread). Still uses `scripts.lib`. |
| `server.py` (webapp) | 683 | Entry point | **LEGACY** | FastAPI web backend. Still uses `scripts.lib`. |

### Pipeline Modules (Imported by Services)

| File | Lines | Type | Status | Description |
|------|-------|------|--------|-------------|
| `video_processor.py` | 648 | Legacy module | **LEGACY** | Logic moved to VideoService. Kept for backward compatibility. |
| `uploader.py` | 313 | Legacy module | **LEGACY** | Logic moved to UploadService. |
| `sync_drive.py` | 197 | Legacy module | **LEGACY** | Logic moved to StorageService. |
| `sync_out.py` | 158 | Legacy module | **LEGACY** | Logic moved to StorageService. |
| `check_burns.py` | 156 | Legacy module | **LEGACY** | Logic moved to VideoService.quality_gate(). |
| `compliance.py` | 179 | Library | **PRODUCTION** | Regex + AI compliance (used by VideoService). |
| `caption_policy.py` | 515 | Library | **PRODUCTION** | Battle-tested regex lexicon (used by VideoService). |
| `transform_video.py` | 867 | Library | **PRODUCTION** | 8 TikTok styles, TextRenderer (used by VideoService). |
| `sidecar_manager.py` | 117 | Utility | **LEGACY** | Logic moved to SidecarAdapter. |

### AI & Analytics (Used by AnalyticsService)

| File | Lines | Type | Status | Description |
|------|-------|------|--------|-------------|
| `ai_growth.py` | 537 | Daily job | **PRODUCTION** | Cached AI growth engine (≤1 call/day). |
| `competitor_scraper.py` | 266 | Daily job | **PRODUCTION** | Apify scraper → competitor tables. |
| `generate_report.py` | 162 | Daily job | **PRODUCTION** | OPS report → daily_report.txt. |
| `reconcile_metrics.py` | 168 | Daily job | **PRODUCTION** | Match uploads to scraped metrics. |

### Infrastructure & Shared (Legacy)

| File | Lines | Type | Status | Description |
|------|-------|------|--------|-------------|
| `lib.py` | 251 | **Legacy shared** | **LEGACY** | Re-exports from services.utils.* for backward compatibility. |
| `db.py` | 448 | Legacy module | **LEGACY** | Replaced by services.infrastructure.database.Database. |
| `config.py` | 345 | Legacy module | **LEGACY** | Replaced by services.infrastructure.config.Config. |
| `setup_tools.py` | 247 | Utility | **PRODUCTION** | Config verification, DB init, seed captions, proxy test. |
| `import_cookies.py` | 169 | Utility | **PRODUCTION** | Browser cookie → TiktokAU pickle. |
| `qr_login.py` | 308 | Utility | **PRODUCTION** | Headless Playwright QR login via proxy. |

---

## TiktokAutoUploader Directory (`/TiktokAutoUploader/`) — **PROTECTED**

*Never modified. Treated as upstream dependency.*

### Upload Engine (Used by Orchestrator via TikTokAdapter)

| File | Lines | Type | Status | Description |
|------|-------|------|--------|-------------|
| `tiktok_uploader/tiktok_v2.py` | 478 | **Core engine** | **PRODUCTION** | Current `upload_video()` with product anchors (type=33). |
| `tiktok_uploader/tiktok.py` | 486 | Legacy engine | **LEGACY** | Old `upload_video()` without product anchors. |
| `tiktok_uploader/Browser.py` | ~200 | Login only | **PRODUCTION** | Undetected-chromedriver wrapper. |
| `tiktok_uploader/cookies.py` | ~100 | Utility | **PRODUCTION** | Pickle load/save for session cookies. |
| `tiktok_uploader/Config.py` | 131 | Config | **PRODUCTION** | Parses config.txt. |
| `tiktok_uploader/bot_utils.py` | 135 | Utility | **PRODUCTION** | Node.js signature gen, AWS SigV4. |
| `tiktok_uploader/tiktok_signature/` | Node.js | External | **PRODUCTION** | Playwright X-Bogus/_signature. |

### API Layer (NOT Used by Orchestrator)

| File | Lines | Type | Status | Description |
|------|-------|------|--------|-------------|
| `api/main.py` | 65 | Entry point | **UNUSED** | FastAPI app with routers. |
| `api/db.py` | ~100 | DB | **UNUSED** | SQLModel + SQLite. |
| `api/models.py` | ~150 | Models | **UNUSED** | SQLModel definitions. |
| `api/schemas.py` | ~100 | Schemas | **UNUSED** | Pydantic models. |
| `api/routers/*.py` | ~500 total | Routes | **UNUSED** | REST endpoints. |
| `api/services/*.py` | ~400 total | Services | **UNUSED** | API services. |

### Scheduler (NOT Used by Orchestrator)

| File | Lines | Type | Status | Description |
|------|-------|------|--------|-------------|
| `scheduler/main.py` | ~200 | Entry point | **UNUSED** | APScheduler with web UI. |
| `scheduler/worker.py` | ~150 | Worker | **UNUSED** | Job execution worker. |

### noVNC (NOT Used)

| File | Lines | Type | Status | Description |
|------|-------|------|--------|-------------|
| `novnc/control_server.py` | ~300 | Service | **UNUSED** | WebSocket → Selenium bridge. |
| `novnc/entrypoint.sh` | ~50 | Script | **UNUSED** | Container entrypoint. |

---

## Webapp Directory (`/webapp/`) — **LEGACY (uses scripts.lib)**

| File | Lines | Type | Status | Description |
|------|-------|------|--------|-------------|
| `server.py` | 683 | Entry point | **LEGACY** | FastAPI backend + static frontend. Uses `scripts.lib`. |
| `static/index.html` | ~500 | Frontend | **PRODUCTION** | Single-page dashboard. |
| `static/style.css` | ~800 | Frontend | **PRODUCTION** | Dark theme, TikTok red accents. |
| `static/app.js` | ~1000 | Frontend | **PRODUCTION** | Frontend logic, chart.js analytics. |

---

## Tests Directory (`/tests/`)

| File | Lines | Type | Status | Description |
|------|-------|------|--------|-------------|
| `conftest.py` | ~50 | Pytest config | **TEST** | Fixtures: temp db, config, sample video. |
| `test_compliance.py` | ~200 | Tests | **TEST** | Regex, banned phrases, AI layer mocking. |
| `test_video_processor.py` | ~300 | Tests | **TEST** | QC guards, sidecar generation, ffmpeg. |
| `test_uploader.py` | ~200 | Tests | **TEST** | Proxy, geo-check, strict mode, retry. |
| `test_sync_out.py` | ~100 | Tests | **TEST** | Drive cleanup logic. |
| `test_analytics.py` | ~150 | Tests | **TEST** | Metrics reconciliation. |
| `test_competitor_scraper.py` | ~150 | Tests | **TEST** | Apify response parsing. |

---

## Summary Statistics

| Category | File Count | Total Lines | Status |
|----------|------------|-------------|--------|
| Services (core) | 7 | ~1,300 | Production |
| Infrastructure (adapters) | 11 | ~1,500 | Production |
| Domain Models | 10 | ~600 | Production |
| Repositories | 7 | ~600 | Production |
| Utilities | 10 | ~800 | Production (1 legacy) |
| Scripts (entry points) | 3 | ~1,500 | Mixed (1 legacy) |
| Pipeline modules (legacy) | 12 | ~3,500 | Legacy (moved to services) |
| AI/Analytics scripts | 4 | ~1,100 | Production |
| Shared legacy | 4 | ~1,300 | Legacy (backward compat) |
| Webapp | 4 | ~3,000 | Legacy (uses scripts.lib) |
| TiktokAutoUploader (engine) | 8 | ~1,500 | Protected |
| TiktokAutoUploader (API/scheduler) | 12 | ~1,500 | Unused |
| Tests | 7 | ~1,000 | Test suite |
| **Total (excl. venv/node_modules)** | **~115** | **~25,000** | |

---

## Module Classification

| Classification | Files | Action |
|----------------|-------|--------|
| **PRODUCTION SERVICES** | services/core/*.py, services/infrastructure/*.py, services/repositories/*.py, services/models/*.py, services/utils/*.py (except analytics.py) | Keep, maintain |
| **PRODUCTION SCRIPTS** | orchestrator.py, scripts/setup_tools.py, scripts/import_cookies.py, scripts/qr_login.py, scripts/compliance.py, scripts/caption_policy.py, scripts/transform_video.py, scripts/ai_growth.py, scripts/competitor_scraper.py, scripts/generate_report.py, scripts/reconcile_metrics.py | Keep, maintain |
| **LEGACY (backward compat)** | scripts/lib.py, scripts/db.py, scripts/config.py, scripts/video_processor.py, scripts/uploader.py, scripts/sync_drive.py, scripts/sync_out.py, scripts/check_burns.py, scripts/sidecar_manager.py, services/utils/analytics.py, scripts/telegram_bot.py, webapp/server.py | Keep for compatibility, migrate in future |
| **PROTECTED** | TiktokAutoUploader/ | Never modify |
| **UNUSED** | TiktokAutoUploader/api/, TiktokAutoUploader/scheduler/, TiktokAutoUploader/novnc/ | Keep as-is (upstream) |
| **TEST ONLY** | tests/*.py | Keep |