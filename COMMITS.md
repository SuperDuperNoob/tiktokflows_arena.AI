# Commits — Phase 15

**Date:** 2026-08-09
**Branch:** main
**Base:** efca850 (Phase 14: Production Deployment Validation)

---

## Planned Commits

### Commit 1: Fix config import in services layer
```
fix: migrate services/utils/paths.py to services.infrastructure.config

Services layer should not import from scripts.config. This eliminates
a duplicate configuration access pattern.
```

### Commit 2: Fix config import in repositories
```
fix: migrate services/repositories/stock_repository.py to services.infrastructure.config

Repositories should use services layer config, not scripts.config.
```

### Commit 3: Fix Telegram bot AI engine reference
```
fix: use AIGrowthEngine instead of non-existent AIEngine in telegram_bot

AIEngine class was removed/merged into ai_growth.py. AIGrowthEngine
provides cached daily AI budget (1 call/day) which the /growth command
must respect to avoid uncontrolled costs.
```

### Commit 4: Add Phase 15 audit documentation
```
docs: add Phase 15 final audit documents

- FINAL_ARCHITECTURE_AUDIT.md: Architecture verification
- CONFIGURATION_AUDIT.md: Config ownership, duplicates, gaps
- PRODUCTION_READINESS.md: Deployment/ops/recovery checklist
- DEAD_CODE_FINAL_REPORT.md: Dead code inventory
- REVIEW_SUMMARY.md: Phase 15 summary
- CHANGED_FILES.md: This file
```

---

## Commit History (After Phase 15)

```
<new> Phase 15: Final Architecture Audit & Release Readiness
efca850 Phase 14: Production Deployment Validation
aecb719 Phase 13: Fix logging error - move secret masking to StructuredFormatter.format()
384fa40 Phase 13: Security Hardening & Long-Term Maintainability
d728170 Phase 12.1: Performance Findings Hardening
fc18cb3 Phase 12: Performance, Scalability & Resource Optimization
```

---

## Files per Commit

| Commit | Files |
|--------|-------|
| 1 | `services/utils/paths.py` |
| 2 | `services/repositories/stock_repository.py` |
| 3 | `scripts/telegram_bot.py` |
| 4 | `FINAL_ARCHITECTURE_AUDIT.md`, `CONFIGURATION_AUDIT.md`, `PRODUCTION_READINESS.md`, `DEAD_CODE_FINAL_REPORT.md`, `REVIEW_SUMMARY.md`, `CHANGED_FILES.md` |

---

## Verification Commands

```bash
# After each commit, verify:
TESTING=1 TIKTOK_MACHINE_CONFIG=config/config.yaml python -m pytest tests/ -v

# Final verification:
TESTING=1 TIKTOK_MACHINE_CONFIG=config/config.yaml timeout 10 python scripts/orchestrator.py
```