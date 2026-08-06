# TikTok Auto-Posting Machine — Technical Debt (Phase 7)

*Updated after Phase 7: Domain Architecture Refinement & Infrastructure Separation.*

---

## Debt Classification

| Priority | Definition |
|----------|------------|
| **CRITICAL** | Production risk, data loss, security, or incorrect behavior |
| **HIGH** | Maintainability blocks, significant duplication, inconsistent behavior |
| **MEDIUM** | Code quality, testability, operational friction |
| **LOW** | Nice-to-have improvements, documentation gaps |

---

## ✅ RESOLVED in Phases 2-7

### Previously CRITICAL — Now Fixed

1. **Two Active Compliance Engines** → **RESOLVED (Phase 2)**
   - Merged `compliance_engine.py` into `compliance.py`
   - Single compliance module used everywhere

2. **Telegram `/growth` Bypasses Daily AI Cache** → **RESOLVED (Phase 2)**
   - Telegram bot now uses `ai_growth.py` with cached AI
   - Respects `max_calls_per_day: 1`

3. **No Validation on Config Load** → **RESOLVED (Phase 2)**
   - `scripts/config.py` (now `services.infrastructure.config.Config`) validates required keys on load
   - Fails fast with clear error messages

4. **Global Config Cache → Stale Config** → **RESOLVED (Phase 2)**
   - `Config` class has `reload()` method
   - Thread-safe singleton with explicit reload

5. **Raw Stock Ledger Migration Duplicated** → **RESOLVED (Phase 2)**
   - Single migration in `services.infrastructure.database.Database._init_schema()`
   - `services.utils.db_utils.ensure_schema()` delegates to it

### Previously HIGH — Now Fixed

6. **Two Orchestrators** → **RESOLVED (Phase 2)**
   - Removed `upload_orchestrator.py`
   - Single `orchestrator.py` as composition root

7. **Two AI Growth Engines** → **RESOLVED (Phase 2)**
   - Merged `ai_engine.py` into `ai_growth.py`
   - Single cached AI module

8. **Three Encoding Constant Sources** → **RESOLVED (Phase 2)**
   - Centralized in `services.infrastructure.config.Config.DEFAULTS`
   - All services use `Config.get_section("encoding")`

9. **Competitor Data in Three Tables** → **PARTIALLY RESOLVED**
   - Analytics uses `competitor_videos` / `competitor_daily`
   - Legacy `competitor_data` still exists for dashboard (LOW priority)

10. **Two Video Upload Implementations** → **RESOLVED**
    - `TiktokAutoUploader/tiktok_v2.py` is the only one used
    - `tiktok.py` remains as legacy but unused by orchestrator

11. **Caption Building in Three Places** → **PARTIALLY RESOLVED**
    - VideoService owns caption generation
    - `transform_video.py` and `ai_growth.py` still have fallbacks (LOW)

12. **Database Access Patterns Inconsistent** → **RESOLVED (Phase 2)**
    - `services.infrastructure.database.Database` with context manager
    - All repositories use `BaseRepository` with connection pooling

13. **No Retry/Dead Letter for Failed Uploads** → **RESOLVED (Phase 3/4)**
    - `UploadService` has retry logic (2x with backoff)
    - Failed uploads moved to `failed/` with `reason.txt`

14. **Proxy Credentials in Plain Text Config** → **PARTIALLY RESOLVED**
    - Still in `config.yaml` but masked in logs
    - Separate secrets file recommended (MEDIUM)

15. **System Events Table Unbounded** → **UNRESOLVED (MEDIUM)**

---

## CURRENT Technical Debt (Post-Phase 7)

### CRITICAL Issues

None currently.

### HIGH Issues

1. **Legacy `scripts/lib.py` Still Exists** (Compatibility Layer)
   - **Location**: `scripts/lib.py` (251 lines)
   - **Impact**: Scripts and tests still depend on it; `services.utils.analytics.py` duplicates business logic
   - **Fix**: Migrate remaining scripts to use services directly, then remove

2. **`services/utils/analytics.py` Contains Business Logic** (Duplicates AnalyticsService)
   - **Location**: `services/utils/analytics.py` (383 lines)
   - **Functions**: `reconcile()`, `build()`, `reconcile_cli()`, `report_cli()`
   - **Impact**: Two implementations of reconciliation and reporting
   - **Fix**: Move CLI entry points to scripts, remove from utilities

3. **`webapp/server.py` and `scripts/telegram_bot.py` Still Use `scripts.lib`**
   - **Impact**: Legacy dependency chain not fully severed
   - **Fix**: Migrate to use services directly

### MEDIUM Issues

4. **`transform_video.py` Monolith** (867 lines)
   - **Location**: `scripts/transform_video.py`
   - **Issues**: Styles, renderer, caption builder, encoding constants, font loading
   - **Fix**: Split into `styles.py`, `renderer.py`, `caption_builder.py`, `encoding.py`, `fonts.py`

5. **Dynamic Imports in Orchestrator** → Hard to Trace
   - **Location**: `orchestrator._run_cycle()` imports inside function
   - **Fix**: Move imports to top; already improved in Phase 7

6. **No Type Hints in Core Modules** → Refactoring Risk
   - **Location**: `scripts/` legacy modules
   - **Fix**: Add type hints to public APIs; use `mypy` in CI

7. **Tests Only Cover Happy Paths** → Regression Risk
   - **Location**: `tests/` — mostly mock-based unit tests
   - **Fix**: Add integration tests with testcontainers or mocked external services

8. **No Health Check Endpoint** → Operations Blindness
   - **Location**: `webapp/server.py` has no `/health` or `/ready`
   - **Fix**: Add `/health` (DB connection, config valid) and `/ready`

9. **Single-Threaded Orchestrator** → No Horizontal Scaling
   - **Location**: `orchestrator.py` runs single loop
   - **Fix**: Consider task queue (Redis/RQ) for render/upload stages

10. **Hardcoded Paths in Multiple Modules** → Deployment Fragility
    - **Location**: `/dev/shm`, `/tmp/tiktok-machine-upload.lock`, `/tmp/tiktok_qr_*.png`
    - **Fix**: Configurable temp/lock directories via `config.yaml`

11. **No Structured Logging** → Debugging Difficulty
    - **Location**: All modules use basic `logging`
    - **Fix**: Structured logging (structlog). Add correlation ID per cycle.

12. **Web UI Config Edit Writes Directly to YAML** → Race Conditions
    - **Location**: `webapp/server.py:update_config()`
    - **Fix**: Config versioning, file locking, or config service

13. **System Events Table Unbounded** → Disk Growth
    - **Location**: `system_events` table, no retention policy
    - **Fix**: Partition by month, add TTL (e.g., keep 90 days)

14. **Proxy Credentials in Plain Text Config** → Security Risk
    - **Location**: `config.yaml:proxy.endpoint` contains `user:pass@host:port`
    - **Fix**: Separate secrets file (`.env`) or secret manager

15. **No Retry Queue for Failed Uploads** → Manual Intervention
    - **Location**: `UploadService` moves to `failed/` but no automated re-queue
    - **Fix**: Add retry queue with exponential backoff, max retries, then dead letter

---

### LOW Issues

16. **Commented-Out Code in TiktokAU** → Noise
17. **Empty/Stub Functions** → Confusion
18. **Inconsistent Naming** → Cognitive Load
19. **Missing Docstrings on Public Functions** → Onboarding Friction
20. **No API Versioning** → Breaking Changes Risk
21. **Git Ignore for Secrets** → Accidental Commit Risk
22. **No Dependency Pinning** → Supply Chain Risk

---

## Debt Summary by Category (Current)

| Category | Critical | High | Medium | Low | Total |
|----------|----------|------|--------|-----|-------|
| Duplication | 0 | 2 | 1 | 1 | 4 |
| Configuration | 0 | 0 | 2 | 2 | 4 |
| Architecture | 0 | 1 | 4 | 0 | 5 |
| Database | 0 | 0 | 1 | 0 | 1 |
| Operations | 0 | 0 | 3 | 0 | 3 |
| Security | 0 | 0 | 2 | 1 | 3 |
| Testing | 0 | 0 | 1 | 0 | 1 |
| Code Quality | 0 | 0 | 2 | 3 | 5 |
| **Total** | **0** | **3** | **16** | **7** | **26** |

**Reduced from 35 to 26 items (26% reduction)** through Phases 2-7.

---

## Recommended Phase 8+ Priority Order

1. **Migrate remaining scripts off `scripts.lib`** — Remove legacy dependency
2. **Remove `services/utils/analytics.py` business logic** — Single source of truth
3. **Migrate `webapp/server.py` and `telegram_bot.py` to services** — Complete decoupling
4. **Add structured logging with correlation IDs** — Observability
5. **Add health checks to webapp** — Operations
6. **Split `transform_video.py`** — Maintainability
7. **Add structured config with secrets separation** — Security
8. **Add system_events TTL** — Disk management
9. **Add retry queue for failed uploads** — Reliability
10. **Type hints + mypy in CI** — Refactoring safety