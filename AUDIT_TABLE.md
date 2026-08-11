# Phase 19 Part 1: Complete Dependency Audit

| MODULE | REAL CONSUMERS | TEST CONSUMERS | EXTERNAL ENTRYPOINTS | CANONICAL REPLACEMENT | DUPLICATE LOGIC? | KEEP/DELETE/WRAP | REASON |
|--------|----------------|----------------|----------------------|------------------------|------------------|------------------|--------|
| scripts/lib.py | scripts/lib.py (self-imports config), scripts/telegram_bot.py (indirect via lib.cfg), scripts/video_processor.py (removed in Phase 18) | tests/test_analytics.py, tests/test_uploader.py (multiple), tests/test_competitor_scraper.py, tests/test_sync_out.py | None | services.utils.* (paths, timezone, quality, stock, burn_log, queue, db_utils, proxy) | YES - re-exports services.utils functions | DELETE | Zero production consumers; all canonical functions in services.utils.*; test imports must be migrated |
| scripts/config.py | scripts/lib.py (only consumer) | None | None | services.infrastructure.config.Config | YES - full duplicate implementation | DELETE | Only consumer was scripts/lib.py; canonical is services.infrastructure.config |
| scripts/db.py | None (no imports found) | None | None | services.infrastructure.database.Database | YES - full duplicate implementation | DELETE | Zero consumers; canonical is services.infrastructure.database |
| scripts/transform_video.py | None (video_processor.py uses services.transform) | None | None | services.transform.video_transformer | YES - full duplicate implementation | DELETE | Zero consumers; canonical is services.transform |
| scripts/caption_policy.py | scripts/video_processor.py (was, now uses services.compliance.caption_policy) | None | None | services/compliance/caption_policy.py (exact copy) | YES - exact duplicate | DELETE | Canonical copied to services/compliance/caption_policy.py; zero consumers |
| scripts/compliance.py | scripts/telegram_bot.py, scripts/setup_tools.py | tests/test_e2e_pipeline.py | None | services/compliance/compliance_engine.py | NO - thin wrapper | WRAP (keep thin) | Thin wrapper delegating to services.compliance.ComplianceEngine; needed for backward compat |
| scripts/check_burns.py | None | None | CLI entrypoint | services.core.video_service.VideoService.quality_gate | NO - thin CLI | KEEP (CLI) | Genuine CLI entrypoint; delegates to service |
| scripts/qr_login.py | None | None | CLI entrypoint | None (operational bootstrap) | NO - standalone | KEEP (CLI) | Operational bootstrap tool for QR login |
| scripts/setup_tools.py | None | None | CLI entrypoint | services.infrastructure.config, services.infrastructure.database | NO - thin CLI | KEEP (CLI) | Setup utility CLI; delegates to services |
| scripts/telegram_bot.py | None | None | Service entrypoint | services.infrastructure.database, services.compliance, services.infrastructure.ai_adapter | NO - service interface | KEEP (Service) | Telegram bot service interface; uses canonical services |
| scripts/video_processor.py | None | tests/test_video_processor.py (tests generate_malay_caption) | CLI entrypoint | services.transform, services.compliance.caption_policy, services.core.video_service | NO - CLI | KEEP (CLI) | Video processing CLI; delegates to services |
| scripts/uploader.py | None | tests/test_uploader.py (tests Uploader legacy class) | CLI entrypoint | services.core.upload_service, services.infrastructure.config, services.utils.proxy | NO - thin CLI | KEEP (CLI) | Upload CLI; legacy Uploader class for test compat |
| scripts/sync_out.py | None | tests/test_sync_out.py (tests SyncOut legacy class) | CLI entrypoint | services.core.storage_service | NO - thin CLI | KEEP (CLI) | Sync out CLI; legacy SyncOut class for test compat |
| scripts/sync_drive.py | None | tests/test_sync_out.py (tests DriveSyncer legacy class) | CLI entrypoint | services.core.storage_service | NO - thin CLI | KEEP (CLI) | Sync drive CLI; legacy DriveSyncer for test compat |
| scripts/ai_growth.py | None | None | CLI entrypoint | services.infrastructure.ai_adapter | NO - thin CLI | KEEP (CLI) | Growth CLI; delegates to AIAdapter |
| scripts/sidecar_manager.py | scripts/video_processor.py | None | Library | services.infrastructure.sidecar_adapter | NO - library | KEEP (Library) | Sidecar I/O library used by video_processor |
| scripts/generate_report.py | None | None | CLI entrypoint | services.core.analytics_service | NO - thin CLI | KEEP (CLI) | Report generation CLI |
| scripts/reconcile_metrics.py | None | None | CLI entrypoint | services.core.analytics_service | NO - thin CLI | KEEP (CLI) | Reconcile CLI |
| scripts/competitor_scraper.py | None | tests/test_competitor_scraper.py | CLI entrypoint | services.infrastructure.competitor_scraper | NO - thin CLI | KEEP (CLI) | Scraper CLI |
| scripts/import_cookies.py | None | None | CLI entrypoint | None (operational bootstrap) | NO - standalone | KEEP (CLI) | Cookie import utility |
| scripts/qr_login.py | None | None | CLI entrypoint | None (operational bootstrap) | NO - standalone | KEEP (CLI) | QR login bootstrap |

## Test Consumers Requiring Migration

| TEST FILE | LEGACY IMPORTS | ACTION |
|-----------|----------------|--------|
| tests/test_analytics.py | `import lib` | Migrate to services.utils.* |
| tests/test_uploader.py | `import lib`, `from lib import check_proxy_exit, is_proxy_transport_error, mask_proxy, normalize_proxy_url` | Migrate to services.utils.proxy |
| tests/test_competitor_scraper.py | `import lib` | Migrate to services.utils.* |
| tests/test_sync_out.py | `import lib`, `from sync_drive import DriveSyncer`, `from sync_out import SyncOut` | Test canonical services.core.storage_service |
| tests/test_uploader.py | `from uploader import Uploader` | Test canonical services.core.upload_service |
| tests/test_video_processor.py | `from video_processor import generate_malay_caption` | Test canonical or keep as integration test |
| tests/test_sync_out.py | `from sync_drive import DriveSyncer`, `from sync_out import SyncOut` | Test canonical services.core.storage_service |
| tests/test_e2e_pipeline.py | `from scripts.compliance import ComplianceEngine`, `from scripts.sidecar_manager import SidecarManager` | Use services.compliance.ComplianceEngine, services.infrastructure.sidecar_adapter |

## Classification Summary

| CLASSIFICATION | COUNT | MODULES |
|----------------|-------|---------|
| DELETE (zero consumers, duplicate logic) | 5 | scripts/lib.py, scripts/config.py, scripts/db.py, scripts/transform_video.py, scripts/caption_policy.py |
| WRAP (thin wrapper, keep for compat) | 1 | scripts/compliance.py |
| KEEP (CLI entrypoint) | 10 | check_burns, qr_login, setup_tools, import_cookies, generate_report, reconcile_metrics, competitor_scraper, ai_growth, sync_out, sync_drive, uploader, video_processor |
| KEEP (Service interface) | 1 | telegram_bot |
| KEEP (Library) | 1 | sidecar_manager |
| KEEP (Operational bootstrap) | 2 | qr_login, import_cookies |