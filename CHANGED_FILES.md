# Phase 19 - Changed Files

## Modified Files (22)

### Tests
1. `tests/conftest.py` - Added `reset_random_state` fixture for test isolation
2. `tests/test_analytics.py` - Migrated from `import lib` to `services.utils.db_utils`
3. `tests/test_uploader.py` `'from lib import check_proxy_exit...` → `from services.utils.proxy import ...`
4. `tests/test_competitor_scraper.py` - Migrated from `import lib` to `services.utils.timezone` and `services.utils.db_utils`
5. `tests/test_sync_out.py` - Migrated from `import lib` to `services.utils.db_utils` and `services.utils.paths`
6. `tests/test_e2e_pipeline.py` - Migrated `scripts.compliance` → `services.compliance`, `scripts.sidecar_manager` → `services.infrastructure.sidecar_adapter`
7. `tests/test_uploader.py` - Migrated from `lib` to `services.utils.proxy`
8. `tests/test_analytics.py` - Full rewrite using `services.utils.db_utils`
9. `tests/test_competitor_scraper.py` - Migrated from `lib` to `services.utils.timezone` and `services.utils.db_utils`
10. `tests/test_sync_out.py` - Migrated from `lib` to `services.utils.db_utils` and `services.utils.paths`
11. `tests/test_e2e_pipeline.py` - Migrated `scripts.compliance` → `services.compliance`, `scripts.sidecar_manager` → `services.infrastructure.sidecar_adapter`

### Scripts
12. `scripts/compliance.py` - Thin wrapper delegating to `services.compliance.ComplianceEngine`
13. `scripts/setup_tools.py` - Already using services (no change needed)
14. `scripts/telegram_bot.py` - Already using services (no change needed)
15. `scripts/video_processor.py` - Already using services (no change needed)

### Services
16. `services/core/video_service.py` - Already using services (no change needed)
17. `services/infrastructure/ai_adapter.py` - Already using services (no change needed)

### Config
18. `tests/conftest.py` - Added random state isolation fixture
19. `tests/e2e_test_env.py` - Already using services (no change needed)
20. `tests/test_video_processor.py` - Already using services (no change needed)

### Webapp
21. `webapp/server.py` - Already using services (no change needed)

### Config
22. `pytest.ini` - Added `TESTING = 1` env variable

## New Files (5)

### Services - Compliance Package
1. `services/compliance/__init__.py` - Exports all compliance public API
2. `services/compliance/caption_policy.py` - Exact copy from scripts/caption_policy.py (canonical)
3. `services/compliance/compliance_engine.py` - Canonical ComplianceEngine with deterministic seed support

### Services - Transform Package
4. `services/transform/__init__.py` - Exports all transform public API
5. `services/transform/video_transformer.py` - Canonical VideoTransformer and TextRenderer

## Deleted Files (5)
1. `scripts/lib.py` - Zero consumers; all utils moved to `services.utils.*`
2. `scripts/config.py` - Zero consumers; canonical is `services.infrastructure.config.Config`
3. `scripts/db.py` - Zero consumers; canonical is `services.infrastructure.database.Database`
4. `scripts/transform_video.py` - Zero consumers; canonical is `services.transform.video_transformer`
5. `scripts/caption_policy.py` - Exact duplicate; canonical is `services/compliance/caption_policy.py`

## Remaining scripts/ (16 files - all legitimate)
| File | Classification | Purpose |
|------|----------------|---------|
| `ai_growth.py` | CLI | Growth CLI; delegates to AIAdapter |
| `check_burns.py` | CLI | Quality gate CLI; delegates to VideoService |
| `competitor_scraper.py` | CLI | Scraper CLI; delegates to CompetitorScraper |
| `compliance.py` | WRAP | Thin wrapper to services.compliance.ComplianceEngine |
| `generate_report.py` | CLI | Report CLI; delegates to AnalyticsService |
| `import_cookies.py` | CLI (bootstrap) | Cookie import utility |
| `operator_cli.py` | CLI | Operational CLI |
| `orchestrator.py` | CLI | Main orchestrator |
| `qr_login.py` | CLI (bootstrap) | QR login utility |
| `reconcile_metrics.py` | CLI | Reconcile CLI; delegates to AnalyticsService |
| `recovery_cli.py` | CLI | Recovery CLI |
| `setup_tools.py` | CLI | Setup utility |
| `sidecar_manager.py` | Library | Sidecar I/O library |
| `sync_drive.py` | CLI | Sync drive CLI; delegates to StorageService |
| `sync_out.py` | CLI | Sync out CLI; delegates to StorageService |
| `telegram_bot.py` | Service | Telegram bot interface |
| `uploader.py` | CLI | Upload CLI; legacy Uploader class for test compat |
| `video_processor.py` | CLI | Video processing CLI; delegates to services |