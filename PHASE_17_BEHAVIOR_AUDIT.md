# Phase 17 Behavior Audit — Real Implementation Comparison

**Date**: 2026-08-09  
**Branch**: main (after Phase 16 completion)  
**Purpose**: Document actual behavioral differences between legacy scripts and services layer implementations

---

## Executive Summary

After inspecting all implementation pairs, the migration status is:

| Capability | Status | Canonical Owner | Legacy Remains |
|------------|--------|----------------|----------------|
| Video Processing | **MERGED** | `services.core.VideoService` | `scripts/video_processor.py` (CLI entrypoint only) |
| Upload/Orchestration | **MERGED** | `services.core.UploadService` | `scripts/uploader.py` (CLI + test compat) |
| Storage/Drive Sync | **MERGED** | `services.core.StorageService` | `scripts/sync_drive.py`, `scripts/sync_out.py` (compat classes) |
| AI/Growth Engine | **MERGED** | `services.infrastructure.AIAdapter` | `scripts/ai_growth.py` (CLI wrapper) |
| Analytics/Reporting | **PARTIAL** | `services.core.AnalyticsService` + `AIAdapter` | `scripts/generate_report.py`, `scripts/competitor_scraper.py` (full impl) |
| Competitor Scraping | **LEGACY ONLY** | **NONE** | `scripts/competitor_scraper.py` (full impl) |
| Reconciliation | **LEGACY ONLY** | **NONE** | `scripts/reconcile_metrics.py` (not migrated) |
| Sidecars | **MERGED** | `services.infrastructure.SidecarAdapter` | `scripts/sidecar_manager.py` (legacy) |
| Database | **PARTIAL** | `services.infrastructure.database.Database` | `scripts/db.py` (legacy class) |
| Config | **MIGRATED** | `services.infrastructure.config.Config` | `scripts/config.py` (legacy class) |
| Utils | **LEGACY** | `services.utils.*` | `scripts/lib.py` (re-exports) |

---

## 1. Video Processing Pipeline

### Comparison: `services.core.VideoService` vs `scripts/video_processor.py`

| Feature | VideoService (716 lines) | VideoProcessor (648 lines) | Status |
|---------|-------------------------|---------------------------|--------|
| **Discovery** | `scan_raw()` ✅ | `scan_raw()` ✅ | **PARITY** |
| **Product Selection** | `pick_product_folder()` ✅ | `pick_product_folder()` ✅ | **PARITY** |
| **Analytics Weights** | `query_analytics_weights()` ✅ | `query_analytics_weights()` ✅ | **PARITY** |
| **Caption Generation** | `generate_malay_caption()` ✅ | `generate_malay_caption()` ✅ | **PARITY** |
| **Style Selection** | `pick_style()` via transform_video ✅ | `pick_style()` via transform_video ✅ | **PARITY** |
| **Caption Rendering** | `SkiaAdapter.render()` ✅ | `TextRenderer.render()` ✅ | **PARITY** |
| **FFmpeg Encoding** | `encode()` via `self._encode()` ✅ | `encode()` with same params ✅ | **PARITY** |
| **Quality Gates** | `quality_gate()` + inline checks ✅ | `quality_gate()` + inline checks ✅ | **PARITY** |
| **Burn Checks** | Frame count + duration ✅ | Frame count + duration ✅ | **PARITY** |
| **Quality Metrics** | MB/s, kbps, frames ✅ | MB/s, kbps, frames ✅ | **PARITY** |
| **Raw Archival** | Move to processed/ + `mark_raw_consumed()` ✅ | Move to processed/ + `lib.mark_raw_consumed()` ✅ | **PARITY** |
| **DB Ledger** | `mark_raw_consumed()` with hash ✅ | `lib.mark_raw_consumed()` with hash ✅ | **PARITY** |
| **Deleted Log** | Writes to `deleted_log()` ✅ | Writes to `lib.deleted_log()` ✅ | **PARITY** |
| **Sidecar Creation** | `SidecarAdapter.write()` ✅ | `SidecarManager.write()` ✅ | **PARITY** |
| **Burn Log** | JSONL with full metadata ✅ | JSONL with full metadata ✅ | **PARITY** |
| **Queue Cleanup** | 24h file age cleanup ✅ | 24h file age cleanup ✅ | **PARITY** |
| **File Locking** | `fcntl.flock` on `/tmp/tiktok-machine-video.lock` ✅ | `fcntl.flock` on `/tmp/tiktok-machine-video.lock` ✅ | **PARITY** |
| **Dry-run Mode** | Supported ✅ | Supported ✅ | **PARITY** |
| **Analytics Weights** | Queries `videos` + `daily_metrics` ✅ | Same SQL queries ✅ | **PARITY** |
| **Trending Sound** | From `competitor_videos` ✅ | Same ✅ | **PARITY** |
| **Error Handling** | Try/except with logging ✅ | Try/except with logging ✅ | **PARITY** |
| **Randomisation** | speed, brightness, contrast, trim, overlay_y ✅ | Same ranges ✅ | **PARITY** |

**Key Differences**:
- VideoService uses `services.utils.paths` functions; VideoProcessor uses `lib.` functions (same underlying implementation)
- VideoService uses `SidecarAdapter`; VideoProcessor uses `SidecarManager` (same interface)
- VideoService uses `services.infrastructure.config.get_config()`; VideoProcessor uses `lib.cfg()`
- VideoService has `process_video()` and `select_video()` stubs (unused); VideoProcessor does not

**Verdict**: **FULL PARITY** - VideoService has complete merged implementation. `scripts/video_processor.py` is now only a CLI entrypoint (has `main()` with lock file and argument parsing).

---

## 2. Upload Pipeline

### Comparison: `services.core.UploadService` vs `scripts/uploader.py`

| Feature | UploadService (363 lines) | Uploader (legacy 313 lines) | Status |
|---------|--------------------------|----------------------------|--------|
| **Queue Discovery** | `SidecarAdapter.find()` ✅ | `SidecarManager.find()` ✅ | **PARITY** |
| **Proxy Config** | `normalize_proxy_url()` + env var ✅ | Same + legacy `normalize_proxy_url()` ✅ | **PARITY** |
| **Proxy Verification** | `check_proxy_exit()` + strict mode ✅ | Same + legacy `check_proxy_exit()` ✅ | **PARITY** |
| **Strict Mode** | `env_flag()` + config ✅ | Same + legacy `env_flag()` ✅ | **PARITY** |
| **Geo Check** | `check_proxy_exit()` with ip-api/ipinfo ✅ | Same ✅ | **PARITY** |
| **Cookie Check** | `check_cookie_expiry()` ✅ | Same ✅ | **PARITY** |
| **Anti-bot Jitter** | `random.randint(5, 90)` ✅ | Same ✅ | **PARITY** |
| **Upload Call** | `TikTokAdapter.upload_video()` ✅ | Direct `tiktok_uploader.tiktok_v2.upload_video()` ✅ | **PARITY** |
| **Retry Logic** | `@retry_with_policy(UPLOAD_POLICY)` (2 retries, exponential backoff) | Manual loop (2 retries, 30s/60s) | **SERVICE MORE ROBUST** |
| **Idempotency** | Video hash + `find_by_video_hash()` ✅ | Same ✅ | **PARITY** |
| **Job State Machine** | Full: DISCOVERED→QUEUED→PROCESSING→UPLOADING→SUCCESS/FAILED/RETRY_PENDING/DEAD_LETTER | None (simple success/fail) | **SERVICE MORE COMPLETE** |
| **Retry Classification** | `RetryableError` vs `FatalError` (proxy transport = fatal) | Proxy transport = no retry, API error = retry | **SERVICE MORE ROBUST** |
| **DB Analytics Logging** | `_log_analytics()` writes to `videos` table ✅ | Same inline SQL ✅ | **PARITY** |
| **Success Cleanup** | `_cleanup_success()` removes sidecars + mp4 + logs ✅ | Same ✅ | **PARITY** |
| **Failure Handling** | `_move_to_failed()` with reason.txt ✅ | Same ✅ | **PARITY** |
| **File Locking** | `fcntl.flock` on `/tmp/tiktok-machine-upload.lock` ✅ | Same ✅ | **PARITY** |
| **Dry-run Mode** | Not explicitly in service (handled by orchestrator) | Supported via CLI ✅ | **LEGACY HAS** |
| **Cookie Age Check** | Logs warning at >12h ✅ | Same ✅ | **PARITY** |
| **Upload Metadata** | Captures title, caption, product_id, sound, hashtags ✅ | Same ✅ | **PARITY** |
| **Safe Caption** | 21-char truncation for TikTok API ✅ | Same ✅ | **PARITY** |

**Key Differences**:
- UploadService has **full job state machine** with audit trail; legacy Uploader has simple success/fail
- UploadService has **structured retry policy** with exponential backoff; legacy has hardcoded 30s/60s
- UploadService **classifies errors** (proxy transport = fatal, API error = retryable); legacy treats all API errors same
- UploadService **tracks retry count** in DB; legacy does not
- Legacy Uploader has `dry_run` support; UploadService expects orchestrator to handle

**Verdict**: **SERVICE IS MORE COMPLETE**. Legacy `scripts/uploader.py` kept as CLI wrapper with backward-compat attributes (`strict_mode`, `geo_check`, `proxy_url`, `verify_proxy()`) for test compatibility.

---

## 3. Storage / Drive Sync

### Comparison: `StorageService` vs `scripts/sync_drive.py` + `scripts/sync_out.py`

| Feature | StorageService | sync_drive.py + sync_out.py | Status |
|---------|---------------|----------------------------|--------|
| **Sync From Drive** | `sync_from_drive()` ✅ | `DriveSyncer.sync()` ✅ | **PARITY** |
| **Sync To Drive** | `sync_to_drive()` ✅ | `SyncOut.sync()` ✅ | **PARITY** |
| **rclone Copy** | `rclone copy` with same excludes ✅ | Same ✅ | **PARITY** |
| **Excludes** | processed/**, failed/**, posted/**, tmp/**, *.lock, burn_log.jsonl, deleted*.log | Same ✅ | **PARITY** |
| **Transfers** | `--transfers 1` ✅ | Same ✅ | **PARITY** |
| **Checkers** | `--checkers 2` ✅ | Same ✅ | **PARITY** |
| **Buffer Size** | `--buffer-size 16M` ✅ | Same ✅ | **PARITY** |
| **Retries** | `--retries 2 --low-level-retries 3` ✅ | Same ✅ | **PARITY** |
| **Log Copy** | `sync_to_drive()` copies logs/ + processed/ ✅ | `SyncOut._copy_logs()` + `_copy_processed()` ✅ | **PARITY** |
| **Remote Cleanup** | Reads `consumed_pending_cleanup()` + `rclone deletefile` ✅ | `SyncOut._delete_remote()` same logic ✅ | **PARITY** |
| **DB Ledger** | `mark_drive_cleaned()` after successful delete ✅ | Same ✅ | **PARITY** |
| **Audit Log** | Writes to `drive_cleanup_log()` ✅ | Same ✅ | **PARITY** |
| **Stock Report** | `get_stock_status()` via `scan_stock()` ✅ | `DriveSyncer` builds same report ✅ | **PARITY** |
| **Dry-run** | Not in service | Legacy has `--dry-run` | **LEGACY HAS** |
| **Stock Warning** | Config-driven `min_stock_warning` ✅ | Same ✅ | **PARITY** |

**Key Differences**:
- StorageService is single class with both directions; legacy has separate `DriveSyncer` and `SyncOut` classes
- Legacy `SyncOut` has `_copy_logs()` and `_copy_processed()` as separate methods; StorageService does both in `sync_to_drive()`
- Legacy `DriveSyncer` takes `config` dict + `Database`; StorageService uses `get_config()` internally

**Verdict**: **FULL PARITY**. Legacy classes kept as compatibility wrappers for test compatibility (`DriveSyncer`, `SyncOut`).

---

## 4. AI / Growth Engine

### Comparison: `AIAdapter` (472 lines) vs `scripts/ai_growth.py` (588 lines) + `scripts/ai_growth.py` legacy

| Feature | AIAdapter | ai_growth.py (legacy) | Status |
|---------|-----------|----------------------|--------|
| **Daily Budget Gate** | `_cached_ai_today()` checks `daily_summary.ai_called_at` ✅ | Same logic ✅ | **PARITY** |
| **AI Call** | `call_ai()` with retries, timeout ✅ | Same ✅ | **PARITY** |
| **Prompt Building** | `_build_prompt()` with full context ✅ | Same prompt ✅ | **PARITY** |
| **Policy Enforcement** | `_enforce_policy()` with caption_policy ✅ | Same ✅ | **PARITY** |
| **JSON Extraction** | `_extract_json()` handles markdown/code blocks ✅ | Same ✅ | **PARITY** |
| **Fallback Pool** | `_fallback()` with 13 templates ✅ | Same 13 templates ✅ | **PARITY** |
| **Daily Budget Save** | `_save_ai_call()` with `keeps_ai` logic ✅ | Same ON CONFLICT logic ✅ | **PARITY** |
| **Analysis** | `_analyze()` with own_performance, rival_gap, views_delta, top_sounds, top_tags, stock ✅ | Same queries ✅ | **PARITY** |
| **Own Performance** | `_own_performance()` with 7-day window ✅ | Same ✅ | **PARITY** |
| **Views Delta** | `_views_delta()` with windowed CTEs ✅ | Same ✅ | **PARITY** |
| **Rival Gap** | `_rival_gap()` from `competitor_daily` ✅ | Same ✅ | **PARITY** |
| **Stock Scan** | `scan_stock()` from utils ✅ | Same ✅ | **PARITY** |
| **Prompt Building** | `_build_prompt()` with all context ✅ | Same string template ✅ | **PARITY** |
| **Policy Enforcement** | `_enforce_policy()` with medical repair, obfuscation, length ✅ | Same ✅ | **PARITY** |
| **Caption Generation** | `generate_captions()` uses growth engine ✅ | Direct in ai_growth | **SERVICE MORE COMPLETE** |
| **Strategy Report** | `generate_strategy()` formats markdown ✅ | Same ✅ | **PARITY** |
| **Compliance Check** | `check_compliance()` with AI ✅ | In separate `compliance.py` | **SERVICE MORE COMPLETE** |
| **Caption Rewrite** | `rewrite_caption()` ✅ | Not in ai_growth | **SERVICE MORE COMPLETE** |
| **Dry-run Mode** | Supported via `dry_run` param ✅ | Supported via CLI ✅ | **PARITY** |
| **Force AI** | `force_ai` param bypasses cache ✅ | `--ai` flag ✅ | **PARITY** |
| **Burn Log Integration** | Reads from `burn_jsonl()` ✅ | Same ✅ | **PARITY** |
| **Fallback Pool** | 13 templates ✅ | Same 13 ✅ | **PARITY** |
| **Caption Deduplication** | `update_preset_pool()` with dedup_key ✅ | Same ✅ | **PARITY** |

**Key Differences**:
- AIAdapter is **more complete**: adds `check_compliance()`, `rewrite_caption()`, `generate_captions()`, `generate_strategy()`
- AIAdapter has **daily budget gate built-in** with cache; legacy uses `--ai` flag only
- Legacy `scripts/ai_growth.py` is now thin CLI wrapper (50 lines) calling `AIAdapter.generate_growth_report()`

**Verdict**: **SERVICE IS MORE COMPLETE**. Legacy `scripts/ai_growth.py` reduced to 50-line CLI wrapper.

---

## 5. Analytics / Reporting

### Comparison: `AnalyticsService` + `AIAdapter` vs `scripts/generate_report.py` + `scripts/competitor_scraper.py` + `scripts/reconcile_metrics.py`

| Feature | Services Layer | Legacy Scripts | Status |
|---------|---------------|----------------|--------|
| **Reconciliation** | `AnalyticsService.reconcile_metrics()` → `services.utils.analytics.reconcile()` | `scripts/reconcile_metrics.py` (full impl) | **LEGACY ONLY** |
| **Ops Report** | `AnalyticsService.generate_ops_report()` → `services.utils.analytics.build()` | `scripts/generate_report.py` (full impl) | **LEGACY ONLY** |
| **Growth Report** | `AIAdapter.generate_growth_report()` | `scripts/ai_growth.py` (now wrapper) | **SERVICE** |
| **Competitor Scraping** | `AnalyticsService.run_daily_jobs()` → `CompetitorScraper` | `scripts/competitor_scraper.py` (full impl) | **LEGACY ONLY** |
| **Report Generation** | `services.utils.analytics.build()` | `scripts/generate_report.py` (full impl) | **LEGACY ONLY** |
| **Competitor Scraper** | `services.core.analytics_service` imports and uses `CompetitorScraper` | `scripts/competitor_scraper.py` (full impl) | **LEGACY ONLY** |
| **Reconcile Metrics** | `services.utils.analytics.reconcile()` | `scripts/reconcile_metrics.py` (full impl) | **LEGACY ONLY** |

**Critical Finding**: **Major business logic still lives in legacy scripts!**
- `scripts/reconcile_metrics.py` - 168 lines, full reconciliation implementation
- `scripts/generate_report.py` - 162 lines, full report generation
- `scripts/competitor_scraper.py` - 265 lines, full Apify integration
- `services.core.AnalyticsService` is mostly **stubs** that delegate to `services.utils.analytics` (which is the old `scripts/lib.py` analytics module!)

**Verdict**: **INCOMPLETE MIGRATION** - Analytics/Reporting/Reconciliation/Competitor scraping still fully implemented in legacy scripts. Services layer has stubs only.

---

## 6. Competitor Scraping

### Comparison: `services.core.AnalyticsService` → `CompetitorScraper` vs `scripts/competitor_scraper.py`

| Feature | Services Layer | Legacy Script | Status |
|---------|---------------|---------------|--------|
| **Apify Integration** | `CompetitorScraper._run_apify()` ✅ | Full implementation ✅ | **PARITY** |
| **Actor ID** | `clockworks/tiktok-scraper` ✅ | Same ✅ | **PARITY** |
| **Batch Profiles** | Single run for all profiles ✅ | Same ✅ | **PARITY** |
| **Polling** | `_wait_for_run()` with 420s timeout ✅ | Same ✅ | **PARITY** |
| **Dataset Fetch** | `_fetch_dataset_items()` ✅ | Same ✅ | **PARITY** |
| **Handle Grouping** | `_group_by_handle()` ✅ | Same ✅ | **PARITY** |
| **Analytics Storage** | `_store()` → `competitor_daily` + `competitor_videos` ✅ | Same ✅ | **PARITY** |
| **Legacy Dashboard** | Also writes to `competitor_data` ✅ | Same ✅ | **PARITY** |
| **Top Sound/Hashtag** | Computed from scraped data ✅ | Same ✅ | **PARITY** |
| **Error Handling** | Try/except with logging ✅ | Same ✅ | **PARITY** |
| **Event Logging** | `db.log_event("SCRAPE_COMPLETE")` ✅ | Same ✅ | **PARITY** |

**Key Finding**: `scripts/competitor_scraper.py` is the **canonical implementation** - it's used directly by `AnalyticsService.run_daily_jobs()`. The services layer doesn't have its own implementation.

**Verdict**: **LEGACY IS CANONICAL**. Need to migrate `CompetitorScraper` to services layer.

---

## 7. Reconciliation

### Comparison: `services.utils.analytics.reconcile()` vs `scripts/reconcile_metrics.py`

| Feature | Services Utils | Legacy Script | Status |
|---------|---------------|---------------|--------|
| **Matching Logic** | Caption + time window (36h) ✅ | Same ✅ | **PARITY** |
| **Caption Normalization** | `_norm()` removes non-word chars ✅ | Same ✅ | **PARITY** |
| **Time Window** | 36 hours ✅ | Same ✅ | **PARITY** |
| **Near Match Logic** | Single closest within 1hr gap ✅ | Same ✅ | **PARITY** |
| **Metrics Copy** | Copies from `competitor_videos` to `daily_metrics` ✅ | Same ✅ | **PARITY** |
| **CLI Entry** | `reconcile_cli()` in utils | `main_reconcile()` in script | **PARITY** |

**Finding**: Reconciliation logic lives in `services.utils.analytics` (which re-exports from `scripts/lib.py` → `scripts/utils/analytics.py`). The legacy script `scripts/reconcile_metrics.py` is a thin CLI wrapper (168 lines) calling the same functions.

**Verdict**: **LOGIC IN SERVICES UTILS**, legacy is thin wrapper. But `services.utils.analytics` is re-exported from `scripts/lib.py` - still legacy dependency.

---

## 8. Report Generation

### Comparison: `services.utils.analytics.build()` vs `scripts/generate_report.py`

| Feature | Services Utils | Legacy Script | Status |
|---------|---------------|---------------|--------|
| **Quality Lines** | `quality_lines()` from burn_log ✅ | Same ✅ | **PARITY** |
| **Stock Lines** | `left_lines()` with scan_stock ✅ | Same ✅ | **PARITY** |
| **Posted Lines** | `posts_per_day()` from `videos` table ✅ | Same ✅ | **PARITY** |
| **Performance Lines** | `performance_lines()` with views_delta, best/worst ✅ | Same ✅ | **PARITY** |
| **Telegram Clamp** | `clamp_telegram()` 3900 chars ✅ | Same ✅ | **PARITY** |
| **Human Formatting** | `human()` for numbers ✅ | Same ✅ | **PARITY** |
| **Timestamp** | `stamp()` with MYT ✅ | Same ✅ | **PARITY** |
| **Output** | `daily_report.txt` ✅ | Same ✅ | **PARITY** |
| **CLI** | `report_cli()` in utils | `main()` in script | **PARITY** |

**Finding**: Report generation logic in `services.utils.analytics` (re-exported from `scripts/lib.py` → `scripts/utils/analytics.py`). Legacy script is 162-line thin CLI wrapper.

**Verdict**: **LOGIC IN SERVICES UTILS**, legacy is thin wrapper. But `services.utils.analytics` is re-exported from `scripts/lib.py`.

---

## 9. Competitor Scraper - Still in Legacy

**Critical**: `scripts/competitor_scraper.py` (265 lines) is the **only implementation** of Apify scraping. It's used directly by `AnalyticsService.run_daily_jobs()`:
```python
from competitor_scraper import CompetitorScraper
scraper = CompetitorScraper(config.get("apify", {}), db)
summary = scraper.scrape_all()
```

**No services-layer equivalent exists.**

---

## 10. Sidecars

### Comparison: `SidecarAdapter` vs `SidecarManager`

| Feature | SidecarAdapter (78 lines) | SidecarManager (117 lines) | Status |
|---------|--------------------------|---------------------------|--------|
| **Read JSON** | `read_json()` ✅ | `read_json()` ✅ | **PARITY** |
| **Read PID** | `read_pid()` (legacy format) ✅ | `read_pid()` ✅ | **PARITY** |
| **Read (prefer JSON)** | `read()` prefers JSON ✅ | Same ✅ | **PARITY** |
| **Sidecar Paths** | `sidecar_paths()` returns tuple ✅ | Same ✅ | **PARITY** |
| **Write** | `write()` creates both .json + .pid ✅ | Same ✅ | **PARITY** |
| **Cleanup** | `cleanup()` removes both ✅ | Same ✅ | **PARITY** |
| **Find Queue** | `find()` returns (mp4, primary, metadata) ✅ | Same ✅ | **PARITY** |

**Key Difference**: SidecarAdapter is 78 lines vs 117 lines - cleaner, no logging in reads. Both use same file format.

**Verdict**: **FULL PARITY**. SidecarAdapter is canonical; SidecarManager kept for legacy compatibility.

---

## 11. Database Layer

### Comparison: `services.infrastructure.database.Database` vs `scripts/db.py`

| Feature | Services DB (448 lines) | Legacy db.py (448 lines) | Status |
|---------|------------------------|-------------------------|--------|
| **Schema** | Same SCHEMA constant ✅ | Same ✅ | **PARITY** |
| **Connection** | `_connect()` with WAL ✅ | Same ✅ | **PARITY** |
| **Schema Init** | `_init_schema()` + migrations ✅ | Same ✅ | **PARITY** |
| **Posts CRUD** | create_post, update_status, get_by_id, get_recent, get_by_product, get_today_count, get_last_post_time, find_by_status, find_by_video_hash, find_by_job_uuid, find_unfinished_jobs, find_retry_pending_jobs, increment_retry_count, set_dead_letter, mark_compliance, update_retry_schedule | create_post, update_post_status, get_posts_today, get_posted_count_today, get_last_post_time | **SERVICE MORE COMPLETE** |
| **Raw Stock** | sync_stock, get_stock_counts, get_unused_videos, mark_used, mark_consumed | sync_raw_stock, get_raw_stock_counts, get_unused_raw_videos, mark_raw_video_used, mark_raw_consumed | **PARITY** |
| **Caption Pool** | create, get_by_id, get_by_product, get_all_for_product, mark_used | add_caption, get_available_captions, mark_caption_used, get_caption_pool_for_product | **PARITY** |
| **Competitor Data** | save_competitor_data, get_top_competitor_posts, get_recent_competitor_data | save_competitor_data, get_top_competitor_posts, get_recent_competitor_data | **PARITY** |
| **Events** | log_event, get_recent | log_event, get_recent_events | **PARITY** |
| **Performance** | get_performance_summary, get_products_due_next | get_performance_summary, get_products_due_next | **PARITY** |
| **Migrations** | Schema version table + migrations | Ad-hoc ALTER TABLE in `_init_schema` | **SERVICE MORE ROBUST** |

**Key Differences**:
- Services DB has **structured migrations** with `schema_version` table
- Services DB has **many more query methods** for job state machine
- Legacy db.py has **ad-hoc migrations** in `_init_schema()`
- Services DB **lacks** `save_competitor_data` bulk insert optimization (has `executemany` in legacy)

**Verdict**: **SERVICE IS MORE ROBUST** for job management; legacy has some bulk insert optimizations. Both have same schema.

---

## 12. Configuration

### Comparison: `services.infrastructure.config.Config` vs `scripts/config.py`

| Feature | Services Config | Legacy Config | Status |
|---------|----------------|---------------|--------|
| **Singleton** | Thread-safe with lock ✅ | Same ✅ | **PARITY** |
| **Config File** | YAML with defaults ✅ | Same ✅ | **PARITY** |
| **Env Overrides** | TIKTOK_PROXY, AI_API_KEY, etc. ✅ | Same ✅ | **PARITY** |
| **Validation** | Required keys + type checking ✅ | Only in TESTING=1 skip | **SERVICE MORE ROBUST** |
| **Path Resolution** | Relative → absolute ✅ | Same ✅ | **PARITY** |
| **Defaults** | Comprehensive DEFAULTS dict ✅ | Same ✅ | **PARITY** |
| **Reload** | `reload()` with lock ✅ | `reload_config()` clears cache | **SERVICE MORE ROBUST** |
| **Access** | `cfg.get("section", "key", default=...)` | Same API ✅ | **PARITY** |
| **Save** | Atomic write with temp file ✅ | Same ✅ | **PARITY** |
| **get_section()** | Returns copy ✅ | Not in legacy | **SERVICE HAS** |
| **Bug** | `get(*path, default)` treats positional as path | Legacy `cfg(*p, default=None)` same bug | **BOTH HAVE BUG** |

**Critical Bug Found**: Both implementations have the same bug where `cfg("section", "key", default=val)` treats `default` as part of the path tuple instead of keyword argument. The `get(*path, default=None)` signature means `default` is captured in `*path` tuple.

**Verdict**: **SERVICE MORE ROBUST** but both have same API bug.

---

## 13. Legacy Modules Still Active

| Module | Lines | Purpose | Status |
|--------|-------|---------|--------|
| `scripts/lib.py` | 351 | Re-exports all utils, config, paths, db, proxy, quality, stock, burn_log, queue | **ACTIVE** - many imports |
| `scripts/db.py` | 448 | Database class with full schema | **ACTIVE** - used by tests, some scripts |
| `scripts/config.py` | 346 | Config class | **ACTIVE** - used by some services utils |
| `scripts/video_processor.py` | 648 | CLI entrypoint for video processing | **ACTIVE** - CLI entrypoint |
| `scripts/sidecar_manager.py` | 117 | Sidecar I/O | **ACTIVE** - used by video_service, upload_service |
| `scripts/config.py` | 346 | Config class | **ACTIVE** - used by services.utils.timezone, quality |
| `scripts/compliance.py` | 179 | Compliance engine (library) | **ACTIVE** - used by telegram_bot, webapp, video_service |
| `scripts/caption_policy.py` | 515 | Caption policy library | **ACTIVE** - used everywhere |
| `scripts/transform_video.py` | 867 | Styles, TextRenderer, pick_style | **ACTIVE** - used by video_service |

---

## Summary: What Still Needs Migration

| Priority | Capability | Current State | Action Needed |
|----------|------------|---------------|---------------|
| **CRITICAL** | Competitor Scraping | Only in `scripts/competitor_scraper.py` | Move `CompetitorScraper` to `services.core` or `services.infrastructure` |
| **CRITICAL** | Reconciliation | Only in `services.utils.analytics` (via `scripts/lib.py`) | Move to `services.core.AnalyticsService` or `services.core.ReconciliationService` |
| **CRITICAL** | Report Generation | Only in `services.utils.analytics` (via `scripts/lib.py`) | Move to `services.core.AnalyticsService` |
| **CRITICAL** | Report CLI | `scripts/generate_report.py` (wrapper) | Keep as CLI wrapper, ensure calls services |
| **HIGH** | Competitor Scraper CLI | `scripts/competitor_scraper.py` (full impl) | Keep as CLI wrapper, ensure calls services |
| **HIGH** | Reconcile Metrics CLI | `scripts/reconcile_metrics.py` (wrapper) | Keep as CLI wrapper |
| **MEDIUM** | Generate Report CLI | `scripts/generate_report.py` (wrapper) | Keep as CLI wrapper |
| **MEDIUM** | Sidecar Manager | `scripts/sidecar_manager.py` (legacy) | Replace all uses with `SidecarAdapter`, then remove |
| **MEDIUM** | Legacy DB | `scripts/db.py` (legacy class) | Replace all uses with `services.infrastructure.database.Database`, then remove |
| **MEDIUM** | Legacy Config | `scripts/config.py` (legacy class) | Replace all uses with `services.infrastructure.config.Config`, then remove |
| **MEDIUM** | Legacy lib.py | `scripts/lib.py` (re-exports) | Replace all imports with direct services imports, then remove |

---

## Test Coverage Gaps

| Area | Test Coverage | Notes |
|------|--------------|-------|
| VideoService | Basic tests in `test_video_processor.py` | Tests legacy VideoProcessor, not VideoService directly |
| UploadService | Good coverage in `test_uploader.py` | Tests legacy Uploader wrapper |
| StorageService | `test_sync_out.py` tests legacy SyncOut | Tests legacy SyncOut class |
| AIAdapter | No direct tests | Only integration via orchestrator |
| AnalyticsService | No direct tests | Only via orchestrator integration |
| CompetitorScraper | `test_competitor_scraper.py` tests legacy class | Tests legacy class |
| Reconciliation | No direct tests | Only via integration |
| Report Generation | No direct tests | Only via integration |

---

## Conclusion

**Phase 16 claimed completion but significant business logic remains in legacy scripts:**

1. **Video Processing**: ✅ Merged (VideoService is canonical)
2. **Upload Pipeline**: ✅ Merged (UploadService is canonical)
3. **Storage/Drive Sync**: ✅ Merged (StorageService is canonical)
4. **AI/Growth**: ✅ Merged (AIAdapter is canonical)
5. **Analytics/Reporting**: ❌ **NOT MIGRATED** - logic in `services.utils.analytics` (re-exported from `scripts/lib.py`)
6. **Competitor Scraping**: ❌ **NOT MIGRATED** - only in `scripts/competitor_scraper.py`
7. **Reconciliation**: ❌ **NOT MIGRATED** - logic in `services.utils.analytics`
7. **Sidecars**: ✅ Merged (SidecarAdapter is canonical)
8. **Database**: ✅ Merged (Database is canonical)
9. **Config**: ✅ Migrated (Config is canonical)

**Remaining legacy modules with business logic that MUST be migrated:**
- `scripts/competitor_scraper.py` (265 lines) - **CRITICAL**
- `services/utils/analytics.py` (383 lines) - **CRITICAL** (re-exported from lib.py)
- `scripts/reconcile_metrics.py` (168 lines) - wrapper only
- `scripts/generate_report.py` (162 lines) - wrapper only
- `scripts/lib.py` (351 lines) - re-export hub
- `scripts/db.py` (448 lines) - legacy DB class
- `scripts/config.py` (346 lines) - legacy Config class
- `scripts/sidecar_manager.py` (117 lines) - legacy sidecar I/O

**Next Steps for Phase 17:**
1. Move `CompetitorScraper` to `services.infrastructure` or `services.core`
2. Move reconciliation logic to `services.core.AnalyticsService` or new `ReconciliationService`
3. Move report generation to `services.core.AnalyticsService`
4. Move analytics utilities to `services.core.analytics` (new module)
4. Replace all `scripts.lib` imports with direct services imports
5. Remove legacy modules after verifying no remaining consumers
6. Add tests for new canonical implementations
7. Create architectural guards to prevent regression

---

*End of PHASE_17_BEHAVIOR_AUDIT.md*