# Dead Code Final Report — Phase 15

**Date:** 2026-08-09
**Branch:** main

---

## Summary

This report documents the final state of dead code in the repository after Phase 15 audit. Per policy, **only proven dead code was removed** (fixes to incorrect imports and references). Uncertain code was preserved.

---

## Confirmed Dead Code (Removed in Phase 15)

### 1. Incorrect Import References (Fixed)

| File | Issue | Fix |
|------|-------|-----|
| `services/utils/paths.py` | Imported from `scripts.config` | Migrated to `services.infrastructure.config` |
| `services/repositories/stock_repository.py` | Imported from `scripts.config` | Migrated to `services.infrastructure.config` |
| `scripts/telegram_bot.py` | Referenced non-existent `AIEngine` class | Changed to `AIGrowthEngine` from `ai_growth.py` |

**No files deleted.** Only import corrections made.

---

## Confirmed Dead Code (Preserved - External/Protected)

### TiktokAutoUploader/ (Protected - Never Modify)

These are part of the protected upstream dependency. They exist in the repo but are **not used by the orchestrator**.

| Path | Status | Reason Preserved |
|------|--------|------------------|
| `TiktokAutoUploader/api/` | Unused | Protected subsystem |
| `TiktokAutoUploader/scheduler/` | Unused | Protected subsystem |
| `TiktokAutoUploader/novnc/` | Unused | Protected subsystem |
| `TiktokAutoUploader/cli.py` | Unused | Protected subsystem |
| `TiktokAutoUploader/youtube_downloader.py` | Unused | Protected subsystem |
| `TiktokAutoUploader/setup.py` | Unused | Protected subsystem |
| `TiktokAutoUploader/tiktok_uploader/tiktok.py` | Legacy v1 | Protected subsystem |
| `TiktokAutoUploader/tiktok_uploader/Video.py` | Unused | Protected subsystem |
| `TiktokAutoUploader/tiktok_uploader/basics.py` | Unused | Protected subsystem |

---

## Legacy Code (Preserved - Backward Compatibility)

### scripts/ - Legacy Pipeline Modules

These are imported by `scripts/lib.py` for backward compatibility with unmigrated scripts and tests.

| File | Lines | Replaced By | Status |
|------|-------|-------------|--------|
| `video_processor.py` | 648 | `services.core.VideoService` | Legacy |
| `uploader.py` | 313 | `services.core.UploadService` | Legacy |
| `sync_drive.py` | 197 | `services.core.StorageService` | Legacy |
| `sync_out.py` | 158 | `services.core.StorageService` | Legacy |
| `check_burns.py` | 156 | `VideoService.quality_gate()` | Legacy |
| `sidecar_manager.py` | 117 | `services.infrastructure.SidecarAdapter` | Legacy |
| `lib.py` | 251 | Re-exports from `services.utils.*` | Compat layer |
| `db.py` | 448 | `services.infrastructure.database.Database` | Legacy |
| `config.py` | 345 | `services.infrastructure.config.Config` | Legacy |

### scripts/ - AI/Analytics (Production)

These are **production** scripts used by the orchestrator daily jobs:

| File | Lines | Purpose | Status |
|------|-------|---------|--------|
| `ai_growth.py` | 537 | Cached AI growth engine (1 call/day) | Production |
| `competitor_scraper.py` | 266 | Apify scraper → competitor tables | Production |
| `generate_report.py` | 162 | OPS report → daily_report.txt | Production |
| `reconcile_metrics.py` | 168 | Match uploads to scraped metrics | Production |

### scripts/ - Libraries (Production)

| File | Lines | Purpose | Status |
|------|-------|---------|--------|
| `compliance.py` | 179 | Regex + AI compliance (used by VideoService) | Production |
| `caption_policy.py` | 515 | Battle-tested regex lexicon | Production |
| `transform_video.py` | 867 | 8 TikTok styles, TextRenderer | Production |

### scripts/ - Utilities (Production)

| File | Lines | Purpose | Status |
|------|-------|---------|--------|
| `setup_tools.py` | 247 | Config verification, DB init, seed captions, proxy test | Production |
| `import_cookies.py` | 169 | Browser cookie → TiktokAU pickle | Production |
| `qr_login.py` | 308 | Headless Playwright QR login via proxy | Production |
| `operator_cli.py` | 187 | Recovery CLI commands | Production |
| `recovery_cli.py` | 151 | Recovery CLI (legacy) | Legacy |

### webapp/ - Legacy Web Interface

| File | Lines | Purpose | Status |
|------|-------|---------|--------|
| `server.py` | 683 | FastAPI backend + static frontend | Legacy (uses `scripts.lib`) |
| `static/index.html` | ~500 | Single-page dashboard | Production |
| `static/style.css` | ~800 | Dark theme, TikTok red accents | Production |
| `static/app.js` | ~1000 | Frontend logic, chart.js analytics | Production |

---

## Unused Functions/Constants (Preserved - Uncertain)

### services/utils/analytics.py (383 lines) - LEGACY

| Function | Used By | Notes |
|----------|---------|-------|
| `reconcile()` | `scripts/reconcile_metrics.py`, `AnalyticsService` | Business logic duplicate |
| `build()` | `scripts/generate_report.py`, `AnalyticsService` | Report generation duplicate |
| `reconcile_cli()` | CLI entry | |
| `report_cli()` | CLI entry | |
| `posted_lines()` | Internal | |
| `left_lines()` | Internal | |
| `quality_lines()` | Internal | |
| `posts_per_day()` | Internal, `webapp/server.py` | Duplicate of `lib.posts_per_day()` |
| `recent_posts()` | Internal, `webapp/server.py` | Duplicate of `lib.recent_posts()` |
| `views_delta()` | Internal, `webapp/server.py` | Duplicate of `lib.views_delta()` |
| `performance_lines()` | Internal | |

**Reason for preservation:** Used by `webapp/server.py` (legacy) and called as CLI by daily jobs. Migration to `AnalyticsService` incomplete.

### scripts/lib.py - Unused Re-exports

| Function | Only Used By | Notes |
|----------|--------------|-------|
| `quality_check()` | `generate_report.py` | |
| `queue_count()` | `generate_report.py` | |
| `recent_posts()` | `generate_report.py`, `ai_growth.py` | |
| `posts_per_day()` | `generate_report.py`, `ai_growth.py` | |
| `own_performance()` | `ai_growth.py` | |
| `views_delta()` | `ai_growth.py` | |
| `latest_handle_snapshot()` | `ai_growth.py` | |
| `rival_gap()` | `ai_growth.py` | |

**Reason for preservation:** Used by production scripts `generate_report.py` and `ai_growth.py`.

### scripts/db.py - Unused Methods

| Method | Only Used By | Notes |
|--------|--------------|-------|
| `get_top_competitor_posts()` | `webapp/server.py` (legacy) | |
| `get_recent_competitor_data()` | None (was `ai_engine.py`) | |
| `get_performance_summary()` | `webapp/server.py` (legacy) | |

### scripts/transform_video.py - Duplicate Constants

| Item | Duplicate Location | Notes |
|------|-------------------|-------|
| `build_overlay_caption()` | `video_processor.generate_malay_caption()` | |
| `CTA_POOL`, `HOOK_POOL`, `EMOJI_POOL`, `BENEFIT_CONNECTORS` | `video_processor.py`, `ai_growth.FALLBACK_POOL` | |
| `FFMPEG_CRF`, `FFMPEG_MAXRATE`, `FFMPEG_PRESET`, `FFMPEG_THREADS` | `video_processor.py` reads from `lib.cfg()` | |
| `MIN_MB_PER_SEC`, `MIN_OUTPUT_FRAMES` | `lib.MIN_MB_PER_SEC`, `lib.MIN_OUTPUT_FRAMES` | |

### scripts/video_processor.py - Unused Return

| Function | Issue |
|----------|-------|
| `query_analytics_weights()` | Returns `(weights, best_sound_id, best_sound_name)` but `pick_product_folder` uses simple `stock * perf` |

### scripts/telegram_bot.py - Empty Stub

| Function | Lines | Issue |
|----------|-------|-------|
| `_handle_unknown()` | 499-500 | Empty stub, no implementation |

---

## Dead Database Columns (Documented, Not Removed)

| Table | Column | Written By | Read By |
|-------|--------|------------|---------|
| `posts` | `description_text` | `orchestrator.create_post()` | Never |
| `posts` | `product_tag_text` | `orchestrator.create_post()` | Never |
| `posts` | `sound_file` | `orchestrator.create_post()` | Never |
| `posts` | `speed_factor` | `orchestrator.create_post()` | Never |
| `posts` | `brightness_shift` | `orchestrator.create_post()` | Never |
| `posts` | `last_analytics_check` | Never | Never |
| `posts` | `notes` | `orchestrator.update_post_status()` | Rarely |
| `caption_pool` | `description_text` | `db.add_caption()` | Never |
| `caption_pool` | `product_tag_text` | `db.add_caption()` | Never |
| `caption_pool` | `original_text` | `db.add_caption()` (on rewrite) | Never |
| `daily_summary` | `total_views` | `ai_growth` upsert | Never |
| `daily_summary` | `total_uploads` | `ai_growth` upsert | Never |
| `daily_summary` | `competitor_gap` | `ai_growth` upsert | Never |

---

## Dead Config Keys (Documented, Not Removed)

| Key | Section | Reason |
|-----|---------|--------|
| `caption_per_video` | `ai` | `ai_growth.py` reads but `video_processor` doesn't use per-video AI captions |
| `growth_locale` | `ai` | Not used anywhere (hardcoded 'ms-MY' in prompts) |
| `compliance_model` | `ai` | `compliance.py` uses `model` from ai config |
| `strategy_model` | `ai` | `ai_engine.py` used it but `ai_growth.py` uses `model` |
| `caption_model` | `ai` | `ai_engine.py` used it but `ai_growth.py` uses `model` |
| `max_caption_tokens` | `ai` | Only in `ai_engine.py` (dead) |
| `max_strategy_tokens` | `ai` | Only in `ai_engine.py` (dead) |
| `compliance_max_tokens` | `ai` | Only in `compliance_engine.py` (dead) |
| `rewrite_rules` | `compliance` | Only in `compliance_engine.py` (dead) |
| `soft_transforms` | `compliance` | Only in `compliance_engine.py` (dead) |
| `creative_misspelling` | `compliance` | Only in `compliance_engine.py` (dead) |
| `yellow_bag_tags` | `products` (in products.json) | Read by `webapp/server.py` only |
| `post_processing_video_path` | TiktokAU config.txt | Not used by orchestrator |
| `IMAGEMAGICK_*` | TiktokAU config.txt | ImageMagick not used (Skia/Playwright) |
| `TIKTOK_DIM` | TiktokAU config.txt | Not used |
| `TMP_YOUTUBE_VIDEO_DIR` | TiktokAU config.txt | Not used |

---

## Orphaned Files (Documented, Not Removed)

| File | Reason |
|------|--------|
| `TiktokAutoUploader/Common Problems Help Readme.md` | Documentation only |
| `TiktokAutoUploader/config.txt` | Config template, not used |
| `TiktokAutoUploader/.deepsource.toml` | DeepSource config |
| `TiktokAutoUploader/.github/FUNDING.yml` | GitHub funding config |
| `TiktokAutoUploader/docker-compose.yml` | Docker for TiktokAU API (not used) |
| `TiktokAutoUploader/README.md` | Documentation |
| `TiktokAutoUploader/changes.txt` | Changelog |
| `content/raw/*/README.txt` | Placeholder files |
| `content/raw/soundtrack/README.txt` | Placeholder |
| `sounds/README.txt` | Placeholder |
| `docs/*.md` | Documentation (keep) |

---

## Commented-Out Code (Documented, Not Removed)

| File | Lines | Description |
|------|-------|-------------|
| `TiktokAutoUploader/tiktok_uploader/tiktok_v2.py` | ~70 (198-270) | Old payload format variations |
| `TiktokAutoUploader/tiktok_uploader/tiktok.py` | ~70 (198-270) | Same commented payload variations |

---

## Verification: No Imports of Dead Code

```bash
# Confirmed: No production code imports these
grep -r "compliance_engine\|ai_engine\|upload_orchestrator" --include="*.py" scripts/ webapp/ services/ orchestrator.py
# → No matches (except in documentation files)

# Confirmed: No production code imports TiktokAutoUploader unused modules
grep -r "TiktokAutoUploader.api\|TiktokAutoUploader.scheduler\|TiktokAutoUploader.novnc" --include="*.py" scripts/ webapp/ services/ orchestrator.py
# → No matches
```

---

## Recommendation

**Do not remove** the preserved dead code in this phase because:

1. **TiktokAutoUploader/** is a protected external dependency
2. **Legacy scripts** (`video_processor.py`, `uploader.py`, etc.) are imported by `scripts/lib.py` which is used by production scripts (`ai_growth.py`, `generate_report.py`, `competitor_scraper.py`, `reconcile_metrics.py`)
3. **webapp/server.py** uses `scripts.lib` and `services.utils.analytics` - migration incomplete
4. **Uncertain code** (duplicate constants, unused DB columns) requires migration of dependent scripts first

**Next phase should:**
1. Migrate `webapp/server.py` to use `services.*` instead of `scripts.lib`
2. Migrate `ai_growth.py`, `generate_report.py`, `competitor_scraper.py`, `reconcile_metrics.py` to use `services.*` directly
3. Remove `scripts/lib.py` and legacy pipeline modules
4. Remove dead DB columns via migration
5. Remove dead config keys

---

## Files Changed in Phase 15 (Dead Code Related)

| File | Change |
|------|--------|
| `services/utils/paths.py` | Fixed import from `scripts.config` → `services.infrastructure.config` |
| `services/repositories/stock_repository.py` | Fixed import from `scripts.config` → `services.infrastructure.config` |
| `scripts/telegram_bot.py` | Fixed `AIEngine` → `AIGrowthEngine` reference |