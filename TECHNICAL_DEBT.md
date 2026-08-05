# TikTok Auto-Posting Machine — Technical Debt

*Prioritized architectural problems discovered during Phase 1 Reality Audit.*

---

## Debt Classification

| Priority | Definition |
|----------|------------|
| **CRITICAL** | Production risk, data loss, security, or incorrect behavior |
| **HIGH** | Maintainability blocks, significant duplication, inconsistent behavior |
| **MEDIUM** | Code quality, testability, operational friction |
| **LOW** | Nice-to-have improvements, documentation gaps |

---

## CRITICAL Issues

### 1. Two Active Compliance Engines → Inconsistent Enforcement
**Location**: `scripts/compliance.py` (pipeline) vs `scripts/compliance_engine.py` (Telegram/webapp)
**Risk**: Captions approved by one engine may be rejected by the other. Pipeline uses regex-first; manual entry uses AI-first.
**Impact**: Non-compliant captions could slip into uploads via manual entry, or compliant captions rejected inconsistently.
**Fix**: Single compliance module used everywhere. Merge logic, pick one pipeline order.

### 2. Telegram `/growth` Bypasses Daily AI Cache → Uncontrolled Costs
**Location**: `scripts/telegram_bot.py:_cmd_growth()` calls `ai_engine.py` (no cache) instead of `ai_growth.py` (cached)
**Risk**: Each `/growth` triggers paid AI call. Config says `max_calls_per_day: 1` but Telegram bypasses this.
**Impact**: Potential 10x+ AI cost overrun if user taps `/growth` repeatedly.
**Fix**: Telegram bot must use `ai_growth.py` with `--ai` flag (respects cache).

### 3. No Validation on Config Load → Silent Misconfiguration
**Location**: `lib.load_config()` returns `{}` on any error (FileNotFound, YAML parse, permission)
**Risk**: Missing config.yaml → empty dict → all defaults used → proxy not configured, AI not configured, etc. System runs but does nothing useful.
**Impact**: Silent failures, hard to debug "why isn't it posting?"
**Fix**: Validate required keys on load, fail fast with clear error messages.

### 4. Global Config Cache → Stale Config Until Restart
**Location**: `lib._CFG` global variable cached on first `config()` call
**Risk**: Config changes (via web UI, manual edit) not picked up until process restart. Orchestrator runs as systemd service — requires `systemctl restart`.
**Impact**: Config changes don't take effect immediately. Web UI "auto-saves" but orchestrator ignores.
**Fix**: Add config reload signal (SIGHUP) or periodic reload, or remove cache.

### 5. Raw Stock Ledger Migration Duplicated → Schema Drift Risk
**Location**: `db.py:_init_schema()` AND `lib.py:ensure_schema()` both migrate `raw_stock`
**Risk**: Two migration paths can diverge. One adds columns the other doesn't. `ensure_schema` called by analytics modules; `_init_schema` by `db.Database`.
**Impact**: Schema inconsistencies, missing columns in one code path.
**Fix**: Single migration function in `lib.py`, called by both.

---

## HIGH Issues

### 6. Two Orchestrators → Maintenance Burden
**Location**: `scripts/orchestrator.py` (systemd) vs `scripts/upload_orchestrator.py` (dead)
**Risk**: Confusion about which is production. Dead code rots, may be accidentally used.
**Fix**: Remove `upload_orchestrator.py` entirely.

### 7. Two AI Growth Engines → Duplicate Logic
**Location**: `scripts/ai_growth.py` (cached, production) vs `scripts/ai_engine.py` (legacy, used by Telegram)
**Risk**: Bug fixes applied to one not the other. Prompt drift.
**Fix**: Merge into single module. Ensure Telegram uses cached version.

### 8. Three Encoding Constant Sources → Parameter Drift
**Location**: `config.yaml:encoding.*`, `transform_video.FFMPEG_*` env vars, `lib.cfg()` + `lib.MIN_*`
**Risk**: Changing `config.yaml` doesn't affect `transform_video` if env vars set. `video_processor` reads from `lib` but `transform_video` (which it imports) reads from env.
**Impact**: FFmpeg params may differ from config.
**Fix**: Single source — `lib.cfg()` everywhere. Remove module-level constants.

### 9. Competitor Data in Three Tables → Storage Waste + Sync Complexity
**Location**: `competitor_data` (legacy), `competitor_videos`, `competitor_daily` (analytics)
**Risk**: Scraper writes to all three. Dashboard reads legacy; growth reads analytics. Triple storage.
**Fix**: Drop `competitor_data`. Update dashboard to read from analytics tables.

### 10. Two Video Upload Implementations → API Confusion
**Location**: `TiktokAutoUploader/tiktok_uploader/tiktok_v2.py` (current) vs `tiktok.py` (legacy)
**Risk**: `cli.py` may use v1. Different payload formats. Bug fixes only in v2.
**Fix**: Remove `tiktok.py`. Update any remaining v1 users.

### 11. Caption Building in Three Places → Inconsistent Captions
**Location**: `video_processor.generate_malay_caption()`, `transform_video.build_overlay_caption()`, `ai_growth.FALLBACK_POOL`
**Risk**: Different hook/CTA/emoji pools, different structure logic. Caption style drifts.
**Fix**: Single `caption_builder.py` module with shared pools.

### 12. Database Access Patterns Inconsistent → Bug Risk
**Location**: `db.py` (class with context manager) vs `lib.py` (raw `get_conn()` + manual close)
**Risk**: `lib.py` functions manually open/close connections; `db.py` uses context manager. Different transaction handling, error paths.
**Fix**: Standardize on one pattern. Prefer `db.py` class interface.

### 13. No Retry/Dead Letter for Failed Uploads → Manual Intervention Required
**Location**: `uploader.py` moves to `failed/` but no automated retry
**Risk**: Transient failures (network blip, TikTok API hiccup) require manual re-queue.
**Fix**: Add retry queue with exponential backoff, max retries, then dead letter.

### 14. Proxy Credentials in Plain Text Config → Security Risk
**Location**: `config.yaml:proxy.endpoint` contains `user:pass@host:port`
**Risk**: Config file in plain text, git-ignored but on disk. Logs masked but memory contains full URL.
**Fix**: Separate secrets file (`.env`) or secret manager. At minimum, split credentials from endpoint.

### 15. System Events Table Unbounded → Disk Growth
**Location**: `system_events` table, no retention policy
**Risk**: Every upload, error, scrape, command logs an event. Grows forever.
**Impact**: SQLite file grows, slower queries, disk pressure.
**Fix**: Partition by month, add TTL (e.g., keep 90 days), or archive old events.

---

## MEDIUM Issues

### 16. `lib.py` God Module (859 lines) → Unmaintainable
**Location**: `scripts/lib.py`
**Issues**: Config, paths, timezone, DB, ledger, quality, proxy, analytics, stock scanning — all in one file.
**Fix**: Split into `config.py`, `paths.py`, `timezone.py`, `database.py`, `ledger.py`, `quality.py`, `proxy.py`, `analytics.py`, `stock.py`.

### 17. `transform_video.py` Monolith (867 lines) → Unmaintainable
**Location**: `scripts/transform_video.py`
**Issues**: Styles, renderer, caption builder, encoding constants, font loading.
**Fix**: Split into `styles.py`, `renderer.py`, `caption_builder.py`, `encoding.py`, `fonts.py`.

### 18. Dynamic Imports in Orchestrator → Hard to Trace
**Location**: `orchestrator._run_cycle()` imports `video_processor`, `uploader`, `check_burns`, `sync_out` inside function
**Issues**: Static analysis fails. Circular import risk. Hard to see dependencies.
**Fix**: Move imports to top of file. Use dependency injection.

### 19. No Type Hints in Core Modules → Refactoring Risk
**Location**: `lib.py`, `db.py`, `video_processor.py`, `uploader.py` — minimal type hints
**Issues**: Hard to refactor safely. IDE support limited.
**Fix**: Add type hints to public APIs. Use `mypy` in CI.

### 20. Tests Only Cover Happy Paths → Regression Risk
**Location**: `tests/` — mostly mock-based unit tests
**Issues**: No integration tests for full pipeline. No proxy failure tests. No cookie expiry tests. No quality gate tests.
**Fix**: Add integration tests with testcontainers or mocked external services.

### 21. No Health Check Endpoint → Operations Blindness
**Location**: `webapp/server.py` has no `/health` or `/ready`
**Issues**: Can't put behind load balancer. No k8s liveness/readiness probes.
**Fix**: Add `/health` (DB connection, config valid) and `/ready` (not paused, proxy OK).

### 22. Single-Threaded Orchestrator → No Horizontal Scaling
**Location**: `orchestrator.py` runs single loop
**Issues**: Can't run multiple workers. If one cycle hangs, whole pipeline stops.
**Fix**: Consider task queue (Redis/RQ) for render/upload stages. At minimum, add watchdog timeout.

### 23. Hardcoded Paths in Multiple Modules → Deployment Fragility
**Location**: `/dev/shm` (video_processor), `/tmp/tiktok-machine-upload.lock` (uploader), `/tmp/tiktok_qr_*.png` (qr_login)
**Issues**: Assumes Linux paths. `/dev/shm` may not exist or be small.
**Fix**: Configurable temp/lock directories via `config.yaml`.

### 24. No Structured Logging → Debugging Difficulty
**Location**: All modules use `logging` with basic format
**Issues**: No JSON logs. No correlation IDs. Can't trace request across modules.
**Fix**: Structured logging (structlog or python-json-logger). Add correlation ID per cycle.

### 25. Web UI Config Edit Writes Directly to YAML → Race Conditions
**Location**: `webapp/server.py:update_config()` writes `config.yaml` directly
**Issues**: No locking. Concurrent edits corrupt file. Orchestrator cache not invalidated.
**Fix**: Config versioning, file locking, or config service with atomic writes.

---

## LOW Issues

### 26. Commented-Out Code in TiktokAU → Noise
**Location**: `tiktok_v2.py` and `tiktok.py` lines 198-270 (~70 lines each)
**Fix**: Remove old payload variations. Keep only current.

### 27. Empty/Stub Functions → Confusion
**Location**: `telegram_bot._handle_unknown()`, `compliance_engine.get_engine()`
**Fix**: Remove or implement.

### 28. Inconsistent Naming → Cognitive Load
**Examples**: `cfg()` vs `config.get()`, `posted_at` (string) vs `posted_at` (datetime), `product_name` vs `product_folder`
**Fix**: Standardize naming conventions.

### 29. Missing Docstrings on Public Functions → Onboarding Friction
**Location**: Most modules have module docstrings but few function docstrings
**Fix**: Add docstrings to all public functions/classes.

### 30. No API Versioning → Breaking Changes Risk
**Location**: `webapp/server.py` endpoints
**Fix**: Add `/api/v1/` prefix. Plan for v2.

### 31. Git Ignore Missing for Secrets → Accidental Commit Risk
**Location**: `.gitignore` should include `config/config.yaml`, `logs/tiktok.db`, `TiktokAutoUploader/CookiesDir/`
**Fix**: Verify `.gitignore` covers all sensitive files.

### 32. No Dependency Pinning in Requirements → Supply Chain Risk
**Location**: `requirements.txt` uses `>=` not `==`
**Fix**: Pin exact versions. Use `pip-tools` or `uv` for lockfiles.

---

## Debt Summary by Category

| Category | Critical | High | Medium | Low | Total |
|----------|----------|------|--------|-----|-------|
| Duplication | 2 | 4 | 2 | 1 | 9 |
| Configuration | 2 | 1 | 1 | 2 | 6 |
| Architecture | 1 | 2 | 4 | 0 | 7 |
| Database | 1 | 1 | 0 | 0 | 2 |
| Operations | 0 | 2 | 2 | 0 | 4 |
| Security | 0 | 1 | 0 | 1 | 2 |
| Testing | 0 | 0 | 1 | 0 | 1 |
| Code Quality | 0 | 0 | 3 | 3 | 6 |
| **Total** | **6** | **11** | **11** | **7** | **35** |

---

## Recommended Phase 2 Priority Order

1. **Fix Critical #2** — Telegram `/growth` cache bypass (cost control)
2. **Fix Critical #1** — Merge compliance engines (correctness)
3. **Fix Critical #3** — Config validation (reliability)
4. **Fix Critical #4** — Config reload (operability)
4. **Fix Critical #5** — Single migration (schema integrity)
5. **Remove High #6** — Delete `upload_orchestrator.py`
6. **Merge High #7** — Unify AI growth engines
7. **Unify High #8** — Single encoding constant source
8. **Drop High #9** — Remove `competitor_data` table
9. **Remove High #10** — Delete `tiktok.py` (legacy upload)
10. **Unify High #11** — Single caption builder
... then Medium issues in order