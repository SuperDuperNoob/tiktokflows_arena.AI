# Legacy Migration Map — Phase 17 (Updated)

**Date:** 2026-08-09
**Branch:** main

---

## Complete Dependency Audit (Verified by Inspection)

| Legacy Module | Current Consumers | Required Replacement | Classification |
|---------------|-------------------|---------------------|----------------|
| `scripts/lib.py` | `scripts/check_burns.py`, `scripts/qr_login.py`, `scripts/setup_tools.py`, `services/utils/timezone.py`, `services/utils/quality.py`, `services/utils/paths.py` (via imports) | `services.utils.*`, `services.infrastructure.config` | **MIGRATE** - Re-export hub |
| `scripts/db.py` | `scripts/competitor_scraper.py` (legacy), `scripts/telegram_bot.py`, `scripts/setup_tools.py`, `scripts/qr_login.py`, `scripts/sidecar_manager.py` | `services.infrastructure.database.Database` | **MIGRATE** - Legacy DB class |
| `scripts/config.py` | `scripts/lib.py` (re-exports), `services/utils/timezone.py`, `services/utils/quality.py`, `scripts/qr_login.py` | `services.infrastructure.config.Config` | **MIGRATE** - Legacy Config class |
| `scripts/video_processor.py` | None (CLI entrypoint only) | `services.core.VideoService` | **MERGE DONE** - VideoService is canonical |
| `scripts/uploader.py` | `scripts/orchestrator.py` (via Uploader class), tests | `services.core.UploadService` | **MERGE DONE** - UploadService is canonical |
| `scripts/sync_drive.py` | `scripts/orchestrator.py`, tests (DriveSyncer class) | `services.core.StorageService` | **MERGE DONE** - StorageService is canonical |
| `scripts/sync_out.py` | `scripts/orchestrator.py`, tests (SyncOut class) | `services.core.StorageService` | **MERGE DONE** - StorageService is canonical |
| `scripts/check_burns.py` | `scripts/orchestrator.py` (CLI) | `services.core.VideoService.quality_gate()` | **MIGRATE** - CLI wrapper |
| `scripts/sidecar_manager.py` | `services.core.VideoService`, `services.core.UploadService` | `services.infrastructure.SidecarAdapter` | **MERGE DONE** - SidecarAdapter is canonical |
| `scripts/ai_growth.py` | `scripts/orchestrator.py` (CLI) | `services.infrastructure.AIAdapter` | **MERGE DONE** - AIAdapter is canonical |
| `scripts/generate_report.py` | `scripts/orchestrator.py` (CLI) | `services.core.AnalyticsService` | **MIGRATE** - CLI wrapper |
| `scripts/competitor_scraper.py` | `services.core.AnalyticsService.run_daily_jobs()`, tests | `services.infrastructure.CompetitorScraper` | **MIGRATE** - Canonical in services |
| `scripts/reconcile_metrics.py` | `scripts/orchestrator.py` (CLI) | `services.core.AnalyticsService` | **MIGRATE** - CLI wrapper |
| `scripts/telegram_bot.py` | `scripts/orchestrator.py` (notifications) | `services.core` + `services.infrastructure` | **KEEP** - Interface layer |
| `scripts/setup_tools.py` | Manual setup utility | `services.*` | **KEEP** - Bootstrap tooling |
| `scripts/qr_login.py` | Manual login utility | `services.*` | **KEEP** - Bootstrap tooling |
| `scripts/compliance.py` | `services.core.VideoService`, `scripts/telegram_bot.py`, `scripts/setup_tools.py`, `webapp/server.py` | `services.utils.compliance` (new) | **KEEP** - Standalone library |
| `scripts/caption_policy.py` | `services.core.VideoService`, `services.infrastructure.AIAdapter`, `services.infrastructure.CompetitorScraper` | `services.utils.caption_policy` (new) | **KEEP** - Standalone library |
| `scripts/transform_video.py` | `services.core.VideoService` | `services.utils.transform_video` (new) | **KEEP** - Standalone library |

---

## Function/Class-Level Migration Status

### Video Processing
| Symbol | Legacy Location | Services Location | Status |
|--------|----------------|-------------------|--------|
| `VideoService` | `scripts/video_processor.py` | `services.core.VideoService` | ✅ **MERGED** |
| `scan_raw()` | `scripts/video_processor.py` | `VideoService.scan_raw()` | ✅ **MERGED** |
| `pick_product_folder()` | `scripts/video_processor.py` | `VideoService.pick_product_folder()` | ✅ **MERGED** |
| `query_analytics_weights()` | `scripts/video_processor.py` | `VideoService.query_analytics_weights()` | ✅ **MERGED** |
| `generate_malay_caption()` | `scripts/video_processor.py` | `VideoService.generate_malay_caption()` | ✅ **MERGED** |
| `encode()` | `scripts/video_processor.py` | `VideoService.encode()` | ✅ **MERGED** |
| `quality_gate()` | `scripts/video_processor.py` | `VideoService.quality_gate()` | ✅ **MERGED** |
| `process_one()` | `scripts/video_processor.py` | `VideoService.process_one()` | ✅ **MERGED** |
| `run()` | `scripts/video_processor.py` | `VideoService.run()` | ✅ **MERGED** |
| `md5_file()` | `scripts/video_processor.py` | `VideoService.md5_file()` | ✅ **MERGED** |
| `probe_resolution()` | `scripts/video_processor.py` | `VideoService.probe_resolution()` | ✅ **MERGED** |
| `frame_count()` | `scripts/video_processor.py` | `VideoService.frame_count()` | ✅ **MERGED** |
| `duration()` | `scripts/video_processor.py` | `VideoService.duration()` | ✅ **MERGED** |

### Upload Pipeline
| Symbol | Legacy Location | Services Location | Status |
|--------|----------------|-------------------|--------|
| `UploadService` | `scripts/uploader.py` | `services.core.UploadService` | ✅ **MERGED** |
| `process_upload_queue()` | `scripts/uploader.py` | `UploadService.process_upload_queue()` | ✅ **MERGED** |
| `verify_proxy()` | `scripts/uploader.py` | `UploadService._verify_proxy()` | ✅ **MERGED** |
| `check_cookie_expiry()` | `scripts/uploader.py` | `UploadService._check_cookie_expiry()` | ✅ **MERGED** |
| `retry_with_policy` | `scripts/uploader.py` (manual) | `services.infrastructure.retry.retry_with_policy` | ✅ **MERGED** |
| `idempotency` | `scripts/uploader.py` (inline) | `UploadService._check_idempotency()` | ✅ **MERGED** |
| `job state machine` | None | `UploadService` (full) | ✅ **SERVICE ONLY** |

### Storage/Drive Sync
| Symbol | Legacy Location | Services Location | Status |
|--------|----------------|-------------------|--------|
| `StorageService` | `scripts/sync_drive.py`, `scripts/sync_out.py` | `services.core.StorageService` | ✅ **MERGED** |
| `sync_from_drive()` | `scripts/sync_drive.py` | `StorageService.sync_from_drive()` | ✅ **MERGED** |
| `sync_to_drive()` | `scripts/sync_out.py` | `StorageService.sync_to_drive()` | ✅ **MERGED** |
| `DriveSyncer` | `scripts/sync_drive.py` | **Compat class in script** | ✅ **LEGACY WRAPPER** |
| `SyncOut` | `scripts/sync_out.py` | **Compat class in script** | ✅ **LEGACY WRAPPER** |

### AI/Growth Engine
| Symbol | Legacy Location | Services Location | Status |
|--------|----------------|-------------------|--------|
| `AIAdapter` | `scripts/ai_growth.py` | `services.infrastructure.AIAdapter` | ✅ **MERGED** |
| `generate_growth_report()` | `scripts/ai_growth.py` | `AIAdapter.generate_growth_report()` | ✅ **MERGED** |
| `_analyze()` | `scripts/ai_growth.py` | `AIAdapter._analyze()` | ✅ **MERGED** |
| `_own_performance()` | `scripts/ai_growth.py` | `AIAdapter._own_performance()` | ✅ **MERGED** |
| `_rival_gap()` | `scripts/ai_growth.py` | `AIAdapter._rival_gap()` | ✅ **MERGED** |
| `_views_delta()` | `scripts/ai_growth.py` | `AIAdapter._views_delta()` | ✅ **MERGED** |
| `_build_prompt()` | `scripts/ai_growth.py` | `AIAdapter._build_prompt()` | ✅ **MERGED** |
| `_enforce_policy()` | `scripts/ai_growth.py` | `AIAdapter._enforce_policy()` | ✅ **MERGED** |
| `_fallback()` | `scripts/ai_growth.py` | `AIAdapter._fallback()` | ✅ **MERGED** |
| `daily budget gate` | `scripts/ai_growth.py` | `AIAdapter._cached_ai_today()` + `_save_ai_call()` | ✅ **MERGED** |

### Analytics/Reporting/Reconciliation
| Symbol | Legacy Location | Services Location | Status |
|--------|----------------|-------------------|--------|
| `reconcile()` | `services.utils.analytics` (via lib) | `AnalyticsService._reconcile()` | ✅ **MERGED** |
| `build()` | `services.utils.analytics` (via lib) | `AnalyticsService._build_report()` | ✅ **MERGED** |
| `posted_lines()` | `services.utils.analytics` | `AnalyticsService._posted_lines()` | ✅ **MERGED** |
| `left_lines()` | `services.utils.analytics` | `AnalyticsService._left_lines()` | ✅ **MERGED** |
| `quality_lines()` | `services.utils.analytics` | `AnalyticsService._quality_lines()` | ✅ **MERGED** |
| `performance_lines()` | `services.utils.analytics` | `AnalyticsService._performance_lines()` | ✅ **MERGED** |
| `posts_per_day()` | `services.utils.analytics` | `AnalyticsService._posts_per_day()` | ✅ **MERGED** |
| `recent_posts()` | `services.utils.analytics` | `AnalyticsService._recent_posts()` | ✅ **MERGED** |
| `views_delta()` | `services.utils.analytics` | `AnalyticsService._views_delta()` | ✅ **MERGED** |

### Competitor Scraping
| Symbol | Legacy Location | Services Location | Status |
|--------|----------------|-------------------|--------|
| `CompetitorScraper` | `scripts/competitor_scraper.py` | `services.infrastructure.CompetitorScraper` | ✅ **MERGED** |
| `scrape_all()` | `scripts/competitor_scraper.py` | `CompetitorScraper.scrape_all()` | ✅ **MERGED** |
| `_run_apify()` | `scripts/competitor_scraper.py` | `CompetitorScraper._run_apify()` | ✅ **MERGED** |
| `_store()` | `scripts/competitor_scraper.py` | `CompetitorScraper._store()` | ✅ **MERGED** |
| `run_daily_scrape()` | `scripts/competitor_scraper.py` | `services.infrastructure.competitor_scraper.run_daily_scrape()` | ✅ **MERGED** |

### Sidecars
| Symbol | Legacy Location | Services Location | Status |
|--------|----------------|-------------------|--------|
| `SidecarAdapter` | `scripts/sidecar_manager.py` | `services.infrastructure.SidecarAdapter` | ✅ **MERGED** |
| `read_json()` | `scripts/sidecar_manager.py` | `SidecarAdapter.read_json()` | ✅ **MERGED** |
| `read_pid()` | `scripts/sidecar_manager.py` | `SidecarAdapter.read_pid()` | ✅ **MERGED** |
| `read()` | `scripts/sidecar_manager.py` | `SidecarAdapter.read()` | ✅ **MERGED** |
| `write()` | `scripts/sidecar_manager.py` | `SidecarAdapter.write()` | ✅ **MERGED** |
| `cleanup()` | `scripts/sidecar_manager.py` | `SidecarAdapter.cleanup()` | ✅ **MERGED** |
| `find()` | `scripts/sidecar_manager.py` | `SidecarAdapter.find()` | ✅ **MERGED** |

### Database
| Symbol | Legacy Location | Services Location | Status |
|--------|----------------|-------------------|--------|
| `Database` class | `scripts/db.py` | `services.infrastructure.database.Database` | ✅ **MERGED** |
| `create_post()` | `scripts/db.py` | `Database.create_post()` | ✅ **MERGED** |
| `update_post_status()` | `scripts/db.py` | `Database.update_post_status()` | ✅ **MERGED** |
| `sync_raw_stock()` | `scripts/db.py` | `Database.sync_raw_stock()` | ✅ **MERGED** |
| `get_unused_raw_videos()` | `scripts/db.py` | `Database.get_unused_raw_videos()` | ✅ **MERGED** |
| `mark_raw_consumed()` | `scripts/db.py` | `services.utils.db_utils.mark_raw_consumed()` | ✅ **MERGED** |
| `save_competitor_data()` | `scripts/db.py` | `Database.save_competitor_data()` | ✅ **MERGED** |
| `get_top_competitor_posts()` | `scripts/db.py` | `Database.get_top_competitor_posts()` | ✅ **MERGED** |
| `log_event()` | `scripts/db.py` | `Database.log_event()` | ✅ **MERGED** |
| `get_performance_summary()` | `scripts/db.py` | `Database.get_performance_summary()` | ✅ **MERGED** |
| `get_products_due_next()` | `scripts/db.py` | `Database.get_products_due_next()` | ✅ **MERGED** |
| **Schema migrations** | Ad-hoc in `_init_schema()` | Structured `schema_version` table | ✅ **SERVICE IMPROVED** |

### Configuration
| Symbol | Legacy Location | Services Location | Status |
|--------|----------------|-------------------|--------|
| `Config` class | `scripts/config.py` | `services.infrastructure.config.Config` | ✅ **MERGED** |
| `get_config()` | `scripts/config.py` | `services.infrastructure.config.get_config()` | ✅ **MERGED** |
| `get(*path, default)` | Bug: positional default | Bug: same (both have it) | ⚠️ **BOTH BUGGY** |
| `reload()` | `scripts/config.py` | `Config.reload()` | ✅ **MERGED** |
| `set()` | `scripts/config.py` | `Config.set()` | ✅ **MERGED** |
| `get_section()` | Not in legacy | `Config.get_section()` | ✅ **SERVICE ONLY** |
| **Validation** | Only in TESTING=1 | Required keys + type checking | ✅ **SERVICE MORE ROBUST** |

---

## Remaining Legacy Consumers (After Phase 17 Migration)

### Still Using Legacy Modules (Need Migration)
| Legacy Module | Remaining Consumers | Migration Needed |
|---------------|---------------------|------------------|
| `scripts/lib.py` | `scripts/check_burns.py`, `scripts/qr_login.py`, `scripts/setup_tools.py`, `services/utils/timezone.py`, `services/utils/quality.py` | Replace imports with direct services imports |
| `scripts/db.py` | `scripts/telegram_bot.py`, `scripts/qr_login.py`, `scripts/setup_tools.py`, `scripts/sidecar_manager.py` | Replace with `services.infrastructure.database.Database` |
| `scripts/config.py` | `scripts/lib.py` (re-exports), `services/utils/timezone.py`, `services/utils/quality.py`, `scripts/qr_login.py` | Replace with `services.infrastructure.config.Config` |
| `scripts/sidecar_manager.py` | `services.core.VideoService`, `services.core.UploadService` | Already using `SidecarAdapter` internally, remove legacy import |
| `scripts/compliance.py` | `services.core.VideoService`, `scripts/telegram_bot.py`, `scripts/setup_tools.py`, `webapp/server.py` | Move to `services.utils.compliance` |
| `scripts/caption_policy.py` | `services.core.VideoService`, `services.infrastructure.AIAdapter` | Move to `services.utils.caption_policy` |
| `scripts/transform_video.py` | `services.core.VideoService` | Move to `services.utils.transform_video` |

### Kept as Legitimate Entry Points (No Migration Needed)
| Module | Reason |
|--------|--------|
| `scripts/telegram_bot.py` | Interface/adapter layer - Telegram commands |
| `scripts/setup_tools.py` | Bootstrap/setup utility |
| `scripts/qr_login.py` | Login/cookie acquisition utility |
| `scripts/video_processor.py` | CLI entrypoint for video processing |
| `scripts/uploader.py` | CLI entrypoint for upload (with test compat) |
| `scripts/sync_drive.py` | CLI entrypoint for Drive sync (with test compat) |
| `scripts/sync_out.py` | CLI entrypoint for Drive cleanup (with test compat) |
| `scripts/check_burns.py` | CLI entrypoint for quality checks |
| `scripts/ai_growth.py` | CLI entrypoint for growth report |
| `scripts/generate_report.py` | CLI entrypoint for ops report |
| `scripts/competitor_scraper.py` | CLI entrypoint for competitor scraping |
| `scripts/reconcile_metrics.py` | CLI entrypoint for reconciliation |

---

## Phase 17 Migration Summary

**Completed in Phase 17:**
1. ✅ `services.infrastructure.CompetitorScraper` - Full Apify integration moved from `scripts/competitor_scraper.py`
2. ✅ `services.core.AnalyticsService` - Full reconciliation + report generation moved from `services.utils.analytics` (which was re-exported from `scripts/lib.py`)
3. ✅ `scripts/competitor_scraper.py` - Now thin CLI wrapper calling services layer
4. ✅ `scripts/reconcile_metrics.py` - Now thin CLI wrapper calling `AnalyticsService.reconcile_metrics()`
5. ✅ `scripts/generate_report.py` - Now thin CLI wrapper calling `AnalyticsService.generate_ops_report()`
6. ✅ All 62 tests pass
7. ✅ Orchestrator starts cleanly

**Remaining for Full Legacy Elimination:**
1. Move `scripts/lib.py` re-exports to direct services imports
2. Move `scripts/db.py` consumers to `services.infrastructure.database.Database`
3. Move `scripts/config.py` consumers to `services.infrastructure.config.Config`
4. Move `scripts/sidecar_manager.py` to `services.infrastructure.SidecarAdapter` (already done in services, just remove legacy import)
5. Move `scripts/compliance.py` to `services.utils.compliance`
6. Move `scripts/caption_policy.py` to `services.utils.caption_policy`
7. Move `scripts/transform_video.py` to `services.utils.transform_video`

---

*End of LEGACY_MIGRATION_MAP.md*