# Legacy Migration Map — Phase 16 (Updated)

**Date:** 2026-08-09
**Branch:** main

---

## Complete Dependency Audit (Verified by Inspection)

| Legacy Module | Current Consumers | Required Replacement | Classification |
|---------------|-------------------|---------------------|----------------|
| `scripts/lib.py` | `scripts/check_burns.py`, `scripts/competitor_scraper.py`, `scripts/generate_report.py`, `scripts/reconcile_metrics.py`, `scripts/sync_out.py`, `scripts/uploader.py`, `scripts/video_processor.py`, `scripts/ai_growth.py`, `webapp/server.py` (for path utils), `services/utils/timezone.py` (imports `config`), `services/utils/quality.py` (imports `config`), `scripts/setup_tools.py`, `scripts/qr_login.py` | `services.utils.*`, `services.infrastructure.config` | **MIGRATE** — 15+ consumers |
| `scripts/db.py` | `scripts/competitor_scraper.py`, `scripts/sync_drive.py`, `scripts/telegram_bot.py`, `scripts/setup_tools.py`, `webapp/server.py` | `services.infrastructure.database.Database`, `services.repositories.*` | **MIGRATE** — 5 consumers |
| `scripts/config.py` | `scripts/lib.py` (re-exports), `services/utils/timezone.py`, `services/utils/quality.py`, `scripts/qr_login.py` | `services.infrastructure.config` | **MIGRATE** — 4 consumers |
| `scripts/video_processor.py` | `scripts/orchestrator.py` (legacy), `services/core/video_service.py` (imports TIKTOK_STYLES, TextRenderer, pick_style) | `services.core.VideoService` | **MERGE** — VideoService is a stub; real logic in legacy |
| `scripts/uploader.py` | `scripts/orchestrator.py` (legacy), `services/core/upload_service.py` (imports SidecarManager) | `services.core.UploadService` | **MERGE** — UploadService has more features; uploader is legacy |
| `scripts/sync_drive.py` | `webapp/server.py` (trigger_sync), `scripts/orchestrator.py` (legacy) | `services.core.StorageService` | **MIGRATE** — 2 consumers |
| `scripts/sync_out.py` | `scripts/orchestrator.py` (legacy) | `services.core.StorageService` | **MIGRATE** — 1 consumer |
| `scripts/check_burns.py` | `scripts/orchestrator.py` (legacy) | `services.core.VideoService.quality_gate` | **MIGRATE** — 1 consumer |
| `scripts/sidecar_manager.py` | `scripts/video_processor.py`, `scripts/uploader.py`, `services/core/video_service.py`, `services/core/upload_service.py`, `webapp/server.py` | `services.infrastructure.SidecarAdapter` | **MIGRATE** — 5 consumers |
| `scripts/ai_growth.py` | `scripts/telegram_bot.py` (via AIGrowthEngine), `webapp/server.py` (reads growth_report.txt), `scripts/orchestrator.py` (daily job) | `services.core.AnalyticsService` + `services.infrastructure.AIAdapter` | **MIGRATE** — 3 consumers |
| `scripts/generate_report.py` | `webapp/server.py` (reads daily_report.txt), `scripts/orchestrator.py` (daily job) | `services.core.AnalyticsService` | **MIGRATE** — 2 consumers |
| `scripts/competitor_scraper.py` | `services/core/analytics_service.py` (daily job), `scripts/orchestrator.py` (daily job) | `services.core.AnalyticsService` | **MIGRATE** — 2 consumers |
| `scripts/reconcile_metrics.py` | `scripts/orchestrator.py` (daily job) | `services.core.AnalyticsService` + `services.repositories.AnalyticsRepository` | **MIGRATE** — 1 consumer |
| `scripts/telegram_bot.py` | `scripts/orchestrator.py` (notification callbacks) | Keep as entrypoint; migrate internal deps | **KEEP** — entrypoint |
| `scripts/qr_login.py` | `scripts/telegram_bot.py`, `webapp/server.py` (relogin) | Keep as utility | **KEEP** — utility |
| `scripts/import_cookies.py` | No direct consumers (standalone) | Keep as utility | **KEEP** — utility |
| `scripts/setup_tools.py` | No direct consumers (standalone) | Keep as utility | **KEEP** — utility |
| `scripts/import_cookies.py` | No direct consumers (standalone) | Keep as utility | **KEEP** — utility |
| `scripts/compliance.py` | `scripts/telegram_bot.py`, `webapp/server.py` | Keep as library | **KEEP** — library |
| `scripts/caption_policy.py` | `scripts/video_processor.py`, `scripts/compliance.py`, `scripts/ai_growth.py`, `services/core/video_service.py` | Keep as library | **KEEP** — library |
| `scripts/transform_video.py` | `scripts/video_processor.py`, `services/core/video_service.py` (imports TIKTOK_STYLES, TextRenderer, pick_style) | Keep as library | **KEEP** — library |
| `scripts/reconcile_metrics.py` | `scripts/orchestrator.py` (daily job) | `services.core.AnalyticsService` + `services.repositories.AnalyticsRepository` | **MIGRATE** — 1 consumer |
| `scripts/generate_report.py` | `webapp/server.py` (reads daily_report.txt), `scripts/orchestrator.py` (daily job) | `services.core.AnalyticsService` | **MIGRATE** — 2 consumers |
| `scripts/ai_growth.py` | `scripts/telegram_bot.py` (via AIGrowthEngine), `webapp/server.py` (reads growth_report.txt), `scripts/orchestrator.py` (daily job) | `services.core.AnalyticsService` + `services.infrastructure.AIAdapter` | **MIGRATE** — 3 consumers |

---

## Symbol-by-Symbol Migration Map for `scripts/lib.py`

| lib Symbol | Current Consumer(s) | Replacement | Status |
|------------|---------------------|-------------|--------|
| `PROJECT_ROOT` | Many | `services.utils.paths.PROJECT_ROOT` | ⬜ |
| `CONFIG_PATH` | Many | `services.infrastructure.config.get_config().config_path` | ⬜ |
| `NON_PRODUCT_DIRS` | `scripts/video_processor.py`, `scripts/ai_growth.py` | `services.utils.paths.NON_PRODUCT_DIRS` | ⬜ |
| `VIDEO_EXTS` | `scripts/video_processor.py`, `scripts/ai_growth.py` | `services.utils.paths.VIDEO_EXTS` | ⬜ |
| `TELEGRAM_LIMIT` | `scripts/telegram_bot.py` | `services.utils.quality.TELEGRAM_LIMIT` | ⬜ |
| `load_config()` | `scripts/lib.py` (internal), `scripts/ai_growth.py` | `services.infrastructure.config.get_config()._data` | ⬜ |
| `config()` | Many | `services.infrastructure.config.get_config()._data` | ⬜ |
| `cfg()` | Many | `services.infrastructure.config.cfg()` | ⬜ |
| `reload_config()` | `scripts/lib.py` (internal) | `services.infrastructure.config.reload_config()` | ⬜ |
| `env_path()` | `scripts/lib.py` (internal) | `services.utils.paths.env_path()` | ⬜ |
| `_resolve()` | `scripts/lib.py` (internal) | `services.utils.paths._resolve()` | ⬜ |
| `drive_root()` | Many | `services.utils.paths.drive_root()` | ⬜ |
| `processed_dir()` | Many | `services.utils.paths.processed_dir()` | ⬜ |
| `failed_dir()` | Many | `services.utils.paths.failed_dir()` | ⬜ |
| `posted_dir()` | Many | `services.utils.paths.posted_dir()` | ⬜ |
| `sounds_dir()` | Many | `services.utils.paths.sounds_dir()` | ⬜ |
| `queue_dir()` | Many | `services.utils.paths.queue_dir()` | ⬜ |
| `db_path()` | Many | `services.utils.paths.db_path()` | ⬜ |
| `preset_txt()` | Many | `services.utils.paths.preset_txt()` | ⬜ |
| `product_txt()` | Many | `services.utils.paths.product_txt()` | ⬜ |
| `burn_jsonl()` | `scripts/ai_growth.py` | `services.utils.paths.burn_jsonl()` | ⬜ |
| `deleted_log()` | `scripts/video_processor.py` | `services.utils.paths.deleted_log()` | ⬜ |
| `success_log()` | `scripts/uploader.py` | `services.utils.paths.success_log()` | ⬜ |
| `failed_log()` | `scripts/uploader.py` | `services.utils.paths.failed_log()` | ⬜ |
| `growth_report()` | `webapp/server.py` | `services.utils.paths.growth_report()` | ⬜ |
| `drive_cleanup_log()` | `webapp/server.py` | `services.utils.paths.drive_cleanup_log()` | ⬜ |
| `daily_report()` | `webapp/server.py` | `services.utils.paths.daily_report()` | ⬜ |
| `TIMEZONE` | `scripts/telegram_bot.py` | `services.utils.timezone.TIMEZONE` | ⬜ |
| `OWN_HANDLE` | `scripts/ai_growth.py`, `services/core/video_service.py` | `services.utils.timezone.OWN_HANDLE` | ⬜ |
| `RIVAL_HANDLE` | `scripts/ai_growth.py`, `services/core/video_service.py` | `services.utils.timezone.RIVAL_HANDLE` | ⬜ |
| `local_tz()` | `scripts/ai_growth.py` | `services.utils.timezone.local_tz()` | ⬜ |
| `local_now()` | `scripts/ai_growth.py` | `services.utils.timezone.local_now()` | ⬜ |
| `local_today()` | `scripts/ai_growth.py` | `services.utils.timezone.local_today()` | ⬜ |
| `utcnow()` | `scripts/ai_growth.py`, `scripts/reconcile_metrics.py` | `services.utils.timezone.utcnow()` | ⬜ |
| `stamp()` | `scripts/ai_growth.py` | `services.utils.timezone.stamp()` | ⬜ |
| `human()` | `scripts/ai_growth.py`, `scripts/generate_report.py` | `services.utils.timezone.human()` | ⬜ |
| `clamp_telegram()` | `webapp/server.py` | `services.utils.quality.clamp_telegram()` | ⬜ |
| `SCHEMA` | `scripts/db.py` (internal) | `services.utils.db_utils.SCHEMA` | ⬜ |
| `get_conn()` | `scripts/generate_report.py`, `scripts/reconcile_metrics.py`, `scripts/ai_growth.py` | `services.utils.db_utils.get_conn()` | ⬜ |
| `RAW_LEDGER_SCHEMA` | None | `services.utils.db_utils.RAW_LEDGER_SCHEMA` | ⬜ |
| `ensure_ledger()` | None | `services.utils.db_utils.ensure_ledger()` | ⬜ |
| `mark_raw_consumed()` | `scripts/video_processor.py`, `scripts/uploader.py` | `services.utils.db_utils.mark_raw_consumed()` | ⬜ |
| `consumed_pending_cleanup()` | `webapp/server.py` | `services.utils.db_utils.consumed_pending_cleanup()` | ⬜ |
| `mark_drive_cleaned()` | `scripts/sync_out.py` | `services.utils.db_utils.mark_drive_cleaned()` | ⬜ |
| `ensure_schema()` | `scripts/generate_report.py`, `scripts/reconcile_metrics.py` | `services.utils.db_utils.ensure_schema()` | ⬜ |
| `MIN_MB_PER_SEC` | `scripts/video_processor.py`, `services/core/video_service.py` | `services.utils.quality.MIN_MB_PER_SEC` | ⬜ |
| `MIN_OUTPUT_FRAMES` | `scripts/video_processor.py`, `services/core/video_service.py` | `services.utils.quality.MIN_OUTPUT_FRAMES` | ⬜ |
| `scan_stock()` | `scripts/ai_growth.py` | `services.utils.stock.scan_stock()` | ⬜ |
| `recent_burns()` | `scripts/check_burns.py` | `services.utils.burn_log.recent_burns()` | ⬜ |
| `quality_check()` | `scripts/generate_report.py` | `services.utils.burn_log.quality_check()` | ⬜ |
| `queue_count()` | `scripts/generate_report.py` | `services.utils.queue.queue_count()` | ⬜ |
| `normalize_proxy_url()` | `scripts/uploader.py`, `scripts/sync_drive.py` | `services.utils.proxy.normalize_proxy_url()` | ⬜ |
| `mask_proxy()` | `scripts/uploader.py`, `scripts/setup_tools.py` | `services.utils.proxy.mask_proxy()` | ⬜ |
| `check_proxy_exit()` | `scripts/uploader.py` | `services.utils.proxy.check_proxy_exit()` | ⬜ |
| `is_proxy_transport_error()` | `scripts/uploader.py` | `services.utils.proxy.is_proxy_transport_error()` | ⬜ |
| `posts_per_day()` | `scripts/generate_report.py` | `services.utils.analytics.posts_per_day()` | ⬜ |
| `recent_posts()` | `scripts/generate_report.py` | `services.utils.analytics.recent_posts()` | ⬜ |
| `views_delta()` | `scripts/generate_report.py`, `scripts/ai_growth.py` | `services.utils.analytics.views_delta()` | ⬜ |
| `own_performance()` | `scripts/ai_growth.py` | `services.utils.analytics.own_performance()` | ⬜ |
| `rival_gap()` | `scripts/ai_growth.py` | `services.utils.analytics.rival_gap()` | ⬜ |
| `env_flag()` | `scripts/uploader.py`, `scripts/telegram_bot.py` | `services.infrastructure.config` or local | ⬜ |
| `posts_per_day` (lib) | `scripts/generate_report.py` | `services.utils.analytics.posts_per_day()` | ⬜ |

---

## Symbol-by-Symbol Migration Map for `scripts/db.py`

| db Symbol | Current Consumer(s) | Replacement | Status |
|-----------|---------------------|-------------|--------|
| `Database` class | `scripts/competitor_scraper.py`, `scripts/sync_drive.py`, `scripts/telegram_bot.py`, `scripts/setup_tools.py`, `webapp/server.py` | `services.infrastructure.database.Database` | ⬜ |
| `Database._connect()` | Internal | `services.infrastructure.database.Database._connect()` | ⬜ |
| `Database._init_schema()` | Internal | `services.infrastructure.database.Database._init_schema()` | ⬜ |
| `Database.create_post()` | None (orchestrator uses service) | `services.repositories.UploadRepository.create()` | ⬜ |
| `Database.update_post_status()` | None | `services.repositories.UploadRepository.update_status()` | ⬜ |
| `Database.get_posts_today()` | `webapp/server.py` | `services.repositories.UploadRepository.get_posts_today()` | ⬜ |
| `Database.get_posted_count_today()` | `webapp/server.py`, `scripts/telegram_bot.py` | `services.repositories.UploadRepository.get_posted_count_today()` | ⬜ |
| `Database.get_last_post_time()` | `scripts/telegram_bot.py` | `services.repositories.UploadRepository.get_last_post_time()` | ⬜ |
| `Database.sync_raw_stock()` | `scripts/sync_drive.py` | `services.repositories.StockRepository.sync_stock()` | ⬜ |
| `Database.get_raw_stock_counts()` | `webapp/server.py`, `scripts/telegram_bot.py` | `services.repositories.StockRepository.get_stock_counts()` | ⬜ |
| `Database.get_unused_raw_videos()` | None | `services.repositories.StockRepository.get_unused_videos()` | ⬜ |
| `Database.mark_raw_video_used()` | None | `services.repositories.StockRepository.mark_used()` | ⬜ |
| `Database.add_caption()` | `webapp/server.py`, `scripts/telegram_bot.py` | `services.repositories.CaptionRepository.add_caption()` | ⬜ |
| `Database.get_available_captions()` | None | `services.repositories.CaptionRepository.get_available_captions()` | ⬜ |
| `Database.mark_caption_used()` | None | `services.repositories.CaptionRepository.mark_caption_used()` | ⬜ |
| `Database.get_caption_pool_for_product()` | `webapp/server.py`, `scripts/telegram_bot.py` | `services.repositories.CaptionRepository.get_caption_pool_for_product()` | ⬜ |
| `Database.save_competitor_data()` | `scripts/competitor_scraper.py` | `services.repositories.AnalyticsRepository.save_competitor_data()` | ⬜ |
| `Database.get_top_competitor_posts()` | None (dead) | `services.repositories.AnalyticsRepository.get_top_competitor_posts()` | ⬜ |
| `Database.get_recent_competitor_data()` | None (dead) | `services.repositories.AnalyticsRepository.get_recent_competitor_data()` | ⬜ |
| `Database.get_performance_summary()` | `webapp/server.py` | `services.repositories.AnalyticsRepository.get_performance_summary()` | ⬜ |
| `Database.get_products_due_next()` | `webapp/server.py`, `scripts/telegram_bot.py` | `services.repositories.UploadRepository.get_products_due_next()` | ⬜ |
| `Database.log_event()` | `webapp/server.py`, `scripts/telegram_bot.py` | `services.repositories.EventRepository.log_event()` | ⬜ |
| `Database.get_recent_events()` | `webapp/server.py`, `scripts/telegram_bot.py` | `services.repositories.EventRepository.get_recent_events()` | ⬜ |

---

## Symbol-by-Symbol Migration Map for `scripts/config.py`

| config Symbol | Current Consumer(s) | Replacement | Status |
|---------------|---------------------|-------------|--------|
| `Config` class | `scripts/lib.py` (re-exports), `services/utils/timezone.py`, `services/utils/quality.py` | `services.infrastructure.config.Config` | ⬜ |
| `Config.get_instance()` | `scripts/lib.py` | `services.infrastructure.config.Config.get_instance()` | ⬜ |
| `Config.reset_instance()` | `scripts/lib.py` | `services.infrastructure.config.Config.reset_instance()` | ⬜ |
| `get_config()` | `scripts/lib.py`, `services/utils/timezone.py`, `services/utils/quality.py`, `scripts/qr_login.py` | `services.infrastructure.config.get_config()` | ⬜ |
| `cfg()` | `scripts/lib.py` (re-exports) | `services.infrastructure.config.cfg()` | ⬜ |
| `reload_config()` | `scripts/lib.py` | `services.infrastructure.config.reload_config()` | ⬜ |

---

## Migration Priority Order (Updated)

### Phase 16a: Configuration Graph Fix (Week 1)
1. **services/utils/timezone.py** — Replace `from config import cfg as _cfg` with `services.infrastructure.config`
2. **services/utils/quality.py** — Replace `from config import cfg as _cfg` with `services.infrastructure.config`
3. **scripts/qr_login.py** — Replace `config` import with `services.infrastructure.config`
4. **scripts/lib.py** — Update to use `services.infrastructure.config` (already done)
5. **scripts/config.py** — After all consumers migrated, can be deleted

### Phase 16b: Video Pipeline Merge (Week 2)
6. **services/core/video_service.py** — Merge real logic from `scripts/video_processor.py` (the VideoService is a stub)
7. **scripts/video_processor.py** — Keep as thin CLI wrapper calling VideoService
8. **scripts/check_burns.py** — Migrate to use VideoService.quality_gate
9. **scripts/sidecar_manager.py** → **services.infrastructure.SidecarAdapter** (already exists, verify parity)

### Phase 16c: Upload Pipeline Merge (Week 3)
10. **services/core/upload_service.py** — Already has more features (job state, retry policy, metrics)
11. **scripts/uploader.py** — Keep as thin CLI wrapper calling UploadService
12. **services/infrastructure/tiktok_adapter.py** — Verify it wraps TiktokAutoUploader correctly

### Phase 16d: Storage Pipeline Merge (Week 4)
13. **services/core/storage_service.py** — Merge logic from `scripts/sync_drive.py` and `scripts/sync_out.py`
14. **scripts/sync_drive.py** — Keep as thin CLI wrapper
15. **scripts/sync_out.py** — Keep as thin CLI wrapper

### Phase 16e: Analytics/AI/Reporting (Week 5)
16. **scripts/ai_growth.py** → Move logic to `services.core.AnalyticsService` + `services.infrastructure.AIAdapter`
17. **scripts/generate_report.py** → Move logic to `services.core.AnalyticsService`
18. **scripts/competitor_scraper.py** → Move to `services.core.AnalyticsService` (or keep as utility called by service)
19. **scripts/reconcile_metrics.py** → Move to `services.repositories.AnalyticsRepository`
20. **scripts/generate_report.py** → Move to `services.core.AnalyticsService`

### Phase 16f: Remaining Configuration Cleanup (Week 6)
21. **scripts/db.py** — After all consumers migrated, delete
22. **scripts/lib.py** — After all consumers migrated, delete
23. **scripts/config.py** — After all consumers migrated, delete

---

## Disposition Codes (Final)

| Module | Disposition | Reason |
|--------|-------------|--------|
| `scripts/lib.py` | **DELETE** | All symbols have replacements in services.utils |
| `scripts/db.py` | **DELETE** | Replaced by services.infrastructure.database + repositories |
| `scripts/config.py` | **DELETE** | Replaced by services.infrastructure.config |
| `scripts/video_processor.py` | **MERGE** | Real logic → services.core.VideoService; keep thin CLI |
| `scripts/uploader.py` | **MERGE** | Real logic → services.core.UploadService; keep thin CLI |
| `scripts/sync_drive.py` | **MERGE** | Real logic → services.core.StorageService; keep thin CLI |
| `scripts/sync_out.py` | **MERGE** | Real logic → services.core.StorageService; keep thin CLI |
| `scripts/check_burns.py` | **MERGE** | Real logic → services.core.VideoService.quality_gate; keep thin CLI |
| `scripts/sidecar_manager.py` | **DELETE** | Replaced by services.infrastructure.SidecarAdapter |
| `scripts/ai_growth.py` | **MERGE** | Real logic → services.core.AnalyticsService + AIAdapter; keep thin CLI |
| `scripts/generate_report.py` | **MERGE** | Real logic → services.core.AnalyticsService; keep thin CLI |
| `scripts/competitor_scraper.py` | **MERGE** | Real logic → services.core.AnalyticsService; keep thin CLI |
| `scripts/reconcile_metrics.py` | **MERGE** | Real logic → services.repositories.AnalyticsRepository; keep thin CLI |
| `scripts/generate_report.py` | **MERGE** | Real logic → services.core.AnalyticsService; keep thin CLI |
| `scripts/telegram_bot.py` | **KEEP** | Entrypoint (interface adapter) |
| `scripts/qr_login.py` | **KEEP** | Utility |
| `scripts/import_cookies.py` | **KEEP** | Utility |
| `scripts/setup_tools.py` | **KEEP** | Utility |
| `scripts/compliance.py` | **KEEP** | Library |
| `scripts/caption_policy.py` | **KEEP** | Library |
| `scripts/transform_video.py` | **KEEP** | Library |
| `scripts/ai_growth.py` | **MERGE** | Real logic → services; keep thin CLI |
| `scripts/reconcile_metrics.py` | **MERGE** | Real logic → repositories; keep thin CLI |
| `scripts/generate_report.py` | **MERGE** | Real logic → services; keep thin CLI |
| `scripts/orchestrator.py` | **KEEP** | Composition root |

---

## TikTok Upload Architecture (Documented)

### Complete Upload Path (Preserved)

```
raw video (content/raw/<product>/xxx.mp4)
    ↓
VideoService.process_one() / VideoProcessor.process_one()
    → load_products(), load_captions()
    → scan_raw(), query_analytics_weights(), pick_product_folder()
    → generate_malay_caption() (uses caption_policy)
    → pick_style() from transform_video.TIKTOK_STYLES
    → TextRenderer.render() → caption PNG (Skia)
    → FFmpeg encode (eof_action=repeat, NOT shortest=1)
    → quality check (MIN_MB_PER_SEC, MIN_OUTPUT_FRAMES)
    → archive raw → content/processed/<product>/
    → mark_raw_consumed() (DB ledger: raw_stock.posted_at)
    → write sidecars (.json + .pid) via SidecarManager/SidecarAdapter
    ↓
content/processed/<product>/xxx.mp4 + sidecars
    ↓
UploadService.process_upload_queue() / Uploader.upload()
    → SidecarManager/SidecarAdapter.find() (newest with sidecar)
    → check_cookie_expiry() (TiktokAutoUploader cookies)
    → verify_proxy() (ip-api.com + ipinfo.io geo check)
    → anti-bot jitter (5-90s)
    → TikTokAdapter.upload_video() / tiktok_uploader.tiktok_v2.upload_video()
        → TiktokAutoUploader/tiktok_uploader/tiktok_v2.py (Playwright + Node.js signatures)
        → session cookies from TiktokAutoUploader/CookiesDir/
        → proxy passed per-call (NOT global HTTP_PROXY)
    → on success:
        → _log_analytics() (writes to videos + daily_metrics tables)
        → cleanup sidecars + mp4
        → mark job SUCCESS
    → on failure:
        → retry with backoff (max 2 for API errors)
        → NO retry on proxy transport errors (protects metered GB)
        → move to failed/ with reason.txt
        → mark job FAILED/RETRY_PENDING/DEAD_LETTER
```

### Protected Components (DO NOT MODIFY)

| Component | Purpose |
|-----------|---------|
| `TiktokAutoUploader/tiktok_uploader/tiktok_v2.py` | Current upload engine (Playwright + Node.js signatures) |
| `TiktokAutoUploader/tiktok_uploader/Browser.py` | Undetected-chromedriver wrapper |
| `TiktokAutoUploader/tiktok_uploader/cookies.py` | Cookie pickle load/save |
| `TiktokAutoUploader/tiktok_uploader/tiktok_signature/` | Node.js X-Bogus/_signature generation |
| `TiktokAutoUploader/CookiesDir/` | Session cookie storage |

### Integration Points

| Caller | Method | Protected Target |
|--------|--------|------------------|
| `scripts/uploader.py:_upload_once()` | `from tiktok_uploader.tiktok_v2 import upload_video` | ✅ |
| `services/infrastructure/tiktok_adapter.py:upload_video()` | `tiktok_uploader.tiktok_v2.upload_video` | ✅ |
| `services/core/upload_service.py:_upload_with_retry()` | `self.tiktok_adapter.upload_video()` | ✅ |

---

## Next Immediate Steps

1. **Fix configuration graph** — Migrate `services/utils/timezone.py`, `services/utils/quality.py`, `scripts/qr_login.py` off `scripts/config`
2. **Merge video pipeline** — Move real logic from `scripts/video_processor.py` into `services/core/video_service.py`
3. **Merge upload pipeline** — Ensure `services.core.UploadService` has all features from `scripts/uploader.py`
4. **Create TikTok upload architecture doc** — `TIKTOK_UPLOAD_ARCHITECTURE.md`
5. **Run tests after each merge** — Ensure no regression

---

## Test Commands

```bash
# Full test suite
TESTING=1 TIKTOK_MACHINE_CONFIG=config/config.yaml python -m pytest tests/ -v

# Orchestrator startup
TESTING=1 TIKTOK_MACHINE_CONFIG=config/config.yaml timeout 10 python scripts/orchestrator.py

# Configuration validation
TESTING=1 TIKTOK_MACHINE_CONFIG=config/config.yaml python -c "from services.infrastructure.config import Config; Config(Path('config/config.yaml'))"
```