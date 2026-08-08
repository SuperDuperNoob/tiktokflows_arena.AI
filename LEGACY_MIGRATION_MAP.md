# Legacy Migration Map — Phase 16

**Date:** 2026-08-09
**Branch:** main

---

## Dependency Audit Table

| Legacy Module | Current Consumers | Required Replacement | Safe to Delete? |
|---------------|-------------------|---------------------|-----------------|
| `scripts/lib.py` | scripts/check_burns.py, scripts/competitor_scraper.py, scripts/generate_report.py, scripts/reconcile_metrics.py, scripts/sync_out.py, scripts/uploader.py, scripts/video_processor.py, scripts/ai_growth.py, webapp/server.py (as `_lib`), services/utils/timezone.py (as `config`), services/utils/quality.py (as `config`), scripts/setup_tools.py | `services.utils.*`, `services.infrastructure.config` | **NO** — 10+ consumers |
| `scripts/db.py` | scripts/competitor_scraper.py, scripts/sync_drive.py, scripts/telegram_bot.py, scripts/setup_tools.py, webapp/server.py | `services.infrastructure.database.Database`, `services.repositories.*` | **NO** — 5 consumers |
| `scripts/config.py` | scripts/lib.py (re-exports), services/utils/timezone.py, services/utils/quality.py, scripts/qr_login.py | `services.infrastructure.config` | **NO** — 4 consumers |
| `scripts/video_processor.py` | scripts/orchestrator.py (via service layer), services/core/video_service.py (imports TIKTOK_STYLES, TextRenderer, pick_style) | `services.core.VideoService` | **NO** — used by VideoService |
| `scripts/uploader.py` | services/core/upload_service.py (imports SidecarManager), scripts/orchestrator.py (legacy) | `services.core.UploadService`, `services.infrastructure.SidecarAdapter` | **NO** — used by UploadService |
| `scripts/sync_drive.py` | webapp/server.py (trigger_sync), scripts/orchestrator.py (legacy) | `services.core.StorageService` | **NO** — used by webapp |
| `scripts/sync_out.py` | scripts/orchestrator.py (legacy) | `services.core.StorageService` | **MAYBE** — only legacy orchestrator |
| `scripts/check_burns.py` | scripts/orchestrator.py (legacy) | `services.core.VideoService.quality_gate` | **MAYBE** — only legacy orchestrator |
| `scripts/sidecar_manager.py` | scripts/video_processor.py, scripts/uploader.py, services/core/video_service.py, services/core/upload_service.py, webapp/server.py | `services.infrastructure.SidecarAdapter` | **NO** — 5 consumers |
| `scripts/ai_growth.py` | scripts/telegram_bot.py (via AIGrowthEngine), webapp/server.py (reads growth_report.txt), scripts/orchestrator.py (daily job) | `services.core.AnalyticsService` + `services.infrastructure.AIAdapter` | **NO** — 3 consumers |
| `scripts/generate_report.py` | webapp/server.py (reads daily_report.txt), scripts/orchestrator.py (daily job) | `services.core.AnalyticsService` | **NO** — 2 consumers |
| `scripts/competitor_scraper.py` | services/core/analytics_service.py (daily job), scripts/orchestrator.py (daily job) | `services.core.AnalyticsService` | **NO** — 2 consumers |
| `scripts/reconcile_metrics.py` | scripts/orchestrator.py (daily job) | `services.core.AnalyticsService` + `services.repositories.AnalyticsRepository` | **NO** — 1 consumer |
| `scripts/telegram_bot.py` | scripts/orchestrator.py (notification callbacks) | Keep as entry point; migrate internal deps | **NO** — entry point |
| `webapp/server.py` | Entry point (FastAPI) | Migrate to use `services/` layer | **NO** — entry point |

---

## Symbol-by-Symbol Migration Map for `scripts/lib.py`

| lib Symbol | Current Consumer(s) | Replacement | Migrated? |
|------------|---------------------|-------------|-----------|
| `PROJECT_ROOT` | Many | `services.utils.paths.PROJECT_ROOT` | ⬜ |
| `CONFIG_PATH` | Many | `services.infrastructure.config.get_config().config_path` | ⬜ |
| `NON_PRODUCT_DIRS` | scripts/video_processor.py, scripts/ai_growth.py | `services.utils.paths.NON_PRODUCT_DIRS` | ⬜ |
| `VIDEO_EXTS` | scripts/video_processor.py, scripts/ai_growth.py | `services.utils.paths.VIDEO_EXTS` | ⬜ |
| `TELEGRAM_LIMIT` | scripts/telegram_bot.py | `services.utils.quality.TELEGRAM_LIMIT` | ⬜ |
| `load_config()` | scripts/lib.py (internal), scripts/ai_growth.py | `services.infrastructure.config.get_config()._data` | ⬜ |
| `config()` | Many | `services.infrastructure.config.get_config()._data` | ⬜ |
| `cfg()` | Many | `services.infrastructure.config.cfg()` | ⬜ |
| `reload_config()` | scripts/lib.py (internal) | `services.infrastructure.config.reload_config()` | ⬜ |
| `env_path()` | scripts/lib.py (internal) | `services.utils.paths.env_path()` | ⬜ |
| `_resolve()` | scripts/lib.py (internal) | `services.utils.paths._resolve()` | ⬜ |
| `drive_root()` | Many | `services.utils.paths.drive_root()` | ⬜ |
| `processed_dir()` | Many | `services.utils.paths.processed_dir()` | ⬜ |
| `failed_dir()` | Many | `services.utils.paths.failed_dir()` | ⬜ |
| `posted_dir()` | Many | `services.utils.paths.posted_dir()` | ⬜ |
| `sounds_dir()` | Many | `services.utils.paths.sounds_dir()` | ⬜ |
| `queue_dir()` | Many | `services.utils.paths.queue_dir()` | ⬜ |
| `db_path()` | Many | `services.utils.paths.db_path()` | ⬜ |
| `preset_txt()` | Many | `services.utils.paths.preset_txt()` | ⬜ |
| `product_txt()` | Many | `services.utils.paths.product_txt()` | ⬜ |
| `burn_jsonl()` | scripts/ai_growth.py | `services.utils.paths.burn_jsonl()` | ⬜ |
| `deleted_log()` | scripts/video_processor.py | `services.utils.paths.deleted_log()` | ⬜ |
| `success_log()` | scripts/uploader.py | `services.utils.paths.success_log()` | ⬜ |
| `failed_log()` | scripts/uploader.py | `services.utils.paths.failed_log()` | ⬜ |
| `growth_report()` | webapp/server.py | `services.utils.paths.growth_report()` | ⬜ |
| `drive_cleanup_log()` | webapp/server.py | `services.utils.paths.drive_cleanup_log()` | ⬜ |
| `daily_report()` | webapp/server.py | `services.utils.paths.daily_report()` | ⬜ |
| `TIMEZONE` | scripts/telegram_bot.py | `services.utils.timezone.TIMEZONE` | ⬜ |
| `OWN_HANDLE` | scripts/ai_growth.py, services/core/video_service.py | `services.utils.timezone.OWN_HANDLE` | ⬜ |
| `RIVAL_HANDLE` | scripts/ai_growth.py, services/core/video_service.py | `services.utils.timezone.RIVAL_HANDLE` | ⬜ |
| `local_tz()` | scripts/ai_growth.py | `services.utils.timezone.local_tz()` | ⬜ |
| `local_now()` | scripts/ai_growth.py | `services.utils.timezone.local_now()` | ⬜ |
| `local_today()` | scripts/ai_growth.py | `services.utils.timezone.local_today()` | ⬜ |
| `utcnow()` | scripts/ai_growth.py, scripts/reconcile_metrics.py | `services.utils.timezone.utcnow()` | ⬜ |
| `stamp()` | scripts/ai_growth.py | `services.utils.timezone.stamp()` | ⬜ |
| `human()` | scripts/ai_growth.py, scripts/generate_report.py | `services.utils.timezone.human()` | ⬜ |
| `clamp_telegram()` | webapp/server.py | `services.utils.quality.clamp_telegram()` | ⬜ |
| `SCHEMA` | scripts/db.py (internal) | `services.utils.db_utils.SCHEMA` | ⬜ |
| `get_conn()` | scripts/generate_report.py, scripts/reconcile_metrics.py, scripts/ai_growth.py | `services.utils.db_utils.get_conn()` | ⬜ |
| `RAW_LEDGER_SCHEMA` | None | `services.utils.db_utils.RAW_LEDGER_SCHEMA` | ⬜ |
| `ensure_ledger()` | None | `services.utils.db_utils.ensure_ledger()` | ⬜ |
| `mark_raw_consumed()` | scripts/video_processor.py, scripts/uploader.py | `services.utils.db_utils.mark_raw_consumed()` | ⬜ |
| `consumed_pending_cleanup()` | webapp/server.py | `services.utils.db_utils.consumed_pending_cleanup()` | ⬜ |
| `mark_drive_cleaned()` | scripts/sync_out.py | `services.utils.db_utils.mark_drive_cleaned()` | ⬜ |
| `ensure_schema()` | scripts/generate_report.py, scripts/reconcile_metrics.py | `services.utils.db_utils.ensure_schema()` | ⬜ |
| `MIN_MB_PER_SEC` | scripts/video_processor.py, services/core/video_service.py | `services.utils.quality.MIN_MB_PER_SEC` | ⬜ |
| `MIN_OUTPUT_FRAMES` | scripts/video_processor.py, services/core/video_service.py | `services.utils.quality.MIN_OUTPUT_FRAMES` | ⬜ |
| `scan_stock()` | scripts/ai_growth.py | `services.utils.stock.scan_stock()` | ⬜ |
| `recent_burns()` | scripts/check_burns.py | `services.utils.burn_log.recent_burns()` | ⬜ |
| `quality_check()` | scripts/generate_report.py | `services.utils.burn_log.quality_check()` | ⬜ |
| `queue_count()` | scripts/generate_report.py | `services.utils.queue.queue_count()` | ⬜ |
| `normalize_proxy_url()` | scripts/uploader.py, scripts/sync_drive.py | `services.utils.proxy.normalize_proxy_url()` | ⬜ |
| `mask_proxy()` | scripts/uploader.py, scripts/setup_tools.py | `services.utils.proxy.mask_proxy()` | ⬜ |
| `check_proxy_exit()` | scripts/uploader.py | `services.utils.proxy.check_proxy_exit()` | ⬜ |
| `is_proxy_transport_error()` | scripts/uploader.py | `services.utils.proxy.is_proxy_transport_error()` | ⬜ |
| `posts_per_day()` | scripts/generate_report.py | `services.utils.analytics.posts_per_day()` | ⬜ |
| `recent_posts()` | scripts/generate_report.py | `services.utils.analytics.recent_posts()` | ⬜ |
| `views_delta()` | scripts/generate_report.py, scripts/ai_growth.py | `services.utils.analytics.views_delta()` | ⬜ |
| `own_performance()` | scripts/ai_growth.py | `services.utils.analytics.own_performance()` | ⬜ |
| `rival_gap()` | scripts/ai_growth.py | `services.utils.analytics.rival_gap()` | ⬜ |

---

## Symbol-by-Symbol Migration Map for `scripts/db.py`

| db Symbol | Current Consumer(s) | Replacement | Migrated? |
|-----------|---------------------|-------------|-----------|
| `Database` class | scripts/competitor_scraper.py, scripts/sync_drive.py, scripts/telegram_bot.py, scripts/setup_tools.py, webapp/server.py | `services.infrastructure.database.Database` | ⬜ |
| `Database._connect()` | Internal | `services.infrastructure.database.Database._connect()` | ⬜ |
| `Database._init_schema()` | Internal | `services.infrastructure.database.Database._init_schema()` | ⬜ |
| `Database.create_post()` | None (orchestrator uses service) | `services.repositories.UploadRepository.create()` | ⬜ |
| `Database.update_post_status()` | None | `services.repositories.UploadRepository.update_status()` | ⬜ |
| `Database.get_posts_today()` | webapp/server.py | `services.repositories.UploadRepository.get_posts_today()` | ⬜ |
| `Database.get_posted_count_today()` | webapp/server.py, scripts/telegram_bot.py | `services.repositories.UploadRepository.get_posted_count_today()` | ⬜ |
| `Database.get_last_post_time()` | scripts/telegram_bot.py | `services.repositories.UploadRepository.get_last_post_time()` | ⬜ |
| `Database.sync_raw_stock()` | scripts/sync_drive.py | `services.repositories.StockRepository.sync_stock()` | ⬜ |
| `Database.get_raw_stock_counts()` | webapp/server.py, scripts/telegram_bot.py | `services.repositories.StockRepository.get_stock_counts()` | ⬜ |
| `Database.get_unused_raw_videos()` | None | `services.repositories.StockRepository.get_unused_videos()` | ⬜ |
| `Database.mark_raw_video_used()` | None | `services.repositories.StockRepository.mark_used()` | ⬜ |
| `Database.add_caption()` | webapp/server.py, scripts/telegram_bot.py | `services.repositories.CaptionRepository.add_caption()` | ⬜ |
| `Database.get_available_captions()` | None | `services.repositories.CaptionRepository.get_available_captions()` | ⬜ |
| `Database.mark_caption_used()` | None | `services.repositories.CaptionRepository.mark_caption_used()` | ⬜ |
| `Database.get_caption_pool_for_product()` | webapp/server.py, scripts/telegram_bot.py | `services.repositories.CaptionRepository.get_caption_pool_for_product()` | ⬜ |
| `Database.save_competitor_data()` | scripts/competitor_scraper.py | `services.repositories.AnalyticsRepository.save_competitor_data()` | ⬜ |
| `Database.get_top_competitor_posts()` | None (dead) | `services.repositories.AnalyticsRepository.get_top_competitor_posts()` | ⬜ |
| `Database.get_recent_competitor_data()` | None (dead) | `services.repositories.AnalyticsRepository.get_recent_competitor_data()` | ⬜ |
| `Database.get_performance_summary()` | webapp/server.py | `services.repositories.AnalyticsRepository.get_performance_summary()` | ⬜ |
| `Database.get_products_due_next()` | webapp/server.py, scripts/telegram_bot.py | `services.repositories.UploadRepository.get_products_due_next()` | ⬜ |
| `Database.log_event()` | webapp/server.py, scripts/telegram_bot.py | `services.repositories.EventRepository.log_event()` | ⬜ |
| `Database.get_recent_events()` | webapp/server.py, scripts/telegram_bot.py | `services.repositories.EventRepository.get_recent_events()` | ⬜ |

---

## Symbol-by-Symbol Migration Map for `scripts/config.py`

| config Symbol | Current Consumer(s) | Replacement | Migrated? |
|---------------|---------------------|-------------|-----------|
| `Config` class | scripts/lib.py (re-exports), services/utils/timezone.py, services/utils/quality.py | `services.infrastructure.config.Config` | ⬜ |
| `Config.get_instance()` | scripts/lib.py | `services.infrastructure.config.Config.get_instance()` | ⬜ |
| `Config.reset_instance()` | scripts/lib.py | `services.infrastructure.config.Config.reset_instance()` | ⬜ |
| `get_config()` | scripts/lib.py, services/utils/timezone.py, services/utils/quality.py, scripts/qr_login.py | `services.infrastructure.config.get_config()` | ⬜ |
| `cfg()` | scripts/lib.py (re-exports) | `services.infrastructure.config.cfg()` | ⬜ |
| `reload_config()` | scripts/lib.py | `services.infrastructure.config.reload_config()` | ⬜ |

---

## Migration Priority Order

1. **webapp/server.py** — Replace `db`, `lib`, `sync_drive`, `sidecar_manager`, `compliance` with services layer
2. **scripts/ai_growth.py** — Replace `lib` imports with `services.utils.*` and `services.infrastructure.*`
3. **scripts/generate_report.py** — Replace `lib` imports with `services.utils.*`
4. **scripts/competitor_scraper.py** — Replace `lib` and `db` imports with services layer
5. **scripts/reconcile_metrics.py** — Replace `lib` imports with `services.utils.*`
6. **scripts/telegram_bot.py** — Replace `db` with repositories, `ai_growth` with service
6. **scripts/config.py** — After all consumers migrated, can be deleted
7. **scripts/db.py** — After all consumers migrated, can be deleted
8. **scripts/lib.py** — After all consumers migrated, can be deleted
9. **Legacy pipeline modules** — After consumers migrated, evaluate deletion
10. **Dead DB columns** — Separate migration after verification
11. **Dead config keys** — Separate audit after migration

---

## Disposition Codes

- **MIGRATE** — Functionality exists in services layer, update imports
- **DELETE** — Dead code, no consumers, can be removed
- **KEEP** — Required for backward compatibility or entry point, documented reason
- **DEFER** — Decision pending further investigation

All symbols start as **MIGRATE** unless proven **DELETE** or **KEEP**.