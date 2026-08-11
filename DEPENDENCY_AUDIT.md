# Phase 19 Dependency Audit

## Overview
Complete dependency audit after Phase 19 legacy boundary elimination.

## Dependency Direction Enforcement

### Allowed Direction (Top-Down)
```
ENTRYPOINTS / INTERFACES (scripts/*)
    ↓
APPLICATION SERVICES (services/core/*)
    ↓
DOMAIN / BUSINESS LOGIC (services/compliance/*, services/transform/*)
    ↓
REPOSITORIES / INFRASTRUCTURE (services/infrastructure/*, services/repositories/*)
    ↓
EXTERNAL SYSTEMS (TiktokAutoUploader, FFmpeg, rclone, Apify, Telegram, SQLite, etc.)
```

### Verified: No Reverse Dependencies
- ✅ services/* does NOT import from scripts/*
- ✅ services/* does NOT import from webapp/*
- ✅ services/core/* does NOT import from scripts/*
- ✅ services/infrastructure/* does NOT import from scripts/*
- ✅ domain logic (compliance, transform) does NOT import from scripts/*

## Module-Level Dependencies

### scripts/ (Entry Points - Thin Wrappers Only)
| Script | Imports From | Purpose |
|--------|-------------|---------|
| scripts/compliance.py | services.compliance | Thin wrapper for backward compatibility |
| scripts/setup_tools.py | services.infrastructure.database, services.infrastructure.config, services.compliance | Setup utility |
| scripts/telegram_bot.py | services.infrastructure.database, services.compliance, services.infrastructure.ai_adapter | Telegram interface |
| scripts/video_processor.py | services.utils.*, services.transform, services.compliance.caption_policy, services.infrastructure.config, services.core.video_service | Video processing CLI |
| scripts/sync_out.py | services.core.storage_service, services.utils.paths, services.utils.db_utils | Sync out CLI |
| scripts/sync_drive.py | services.core.storage_service | Sync drive CLI |
| scripts/uploader.py | services.core.upload_service, services.infrastructure.config, services.utils.proxy | Upload CLI |
| scripts/ai_growth.py | services.infrastructure.ai_adapter | AI growth CLI |
| scripts/check_burns.py | services.core.video_service, services.utils.paths | Burn check CLI |
| scripts/generate_report.py | services.core.analytics_service, services.utils.paths | Report CLI |
| scripts/reconcile_metrics.py | services.core.analytics_service, services.utils.paths | Reconcile CLI |
| scripts/competitor_scraper.py | services.infrastructure.competitor_scraper, services.infrastructure.database, services.infrastructure.config | Scraper CLI |
| scripts/qr_login.py | (stdlib only) | QR login - standalone |
| scripts/import_cookies.py | (stdlib only) | Cookie import - standalone |
| scripts/ai_growth.py | services.infrastructure.ai_adapter | AI growth CLI |
| scripts/sidecar_manager.py | services.infrastructure.sidecar_adapter | Sidecar I/O library |

### services/ (Canonical Implementations)
| Module | Dependencies |
|--------|-------------|
| services/compliance/caption_policy.py | stdlib only (hashlib, random, re, unicodedata) |
| services/compliance/compliance_engine.py | services.compliance.caption_policy, stdlib (logging, requests, json) |
| services/transform/video_transformer.py | stdlib, skia (optional), playwright (optional) |
| services/core/video_service.py | services.repositories, services.models, services.infrastructure.*, services.utils.*, services.compliance.caption_policy, services.transform |
| services/core/upload_service.py | services.repositories, services.infrastructure.* |
| services/core/storage_service.py | services.infrastructure.rclone_adapter, services.utils.* |
| services/infrastructure/database.py | stdlib (sqlite3, json, datetime, contextlib) |
| services/infrastructure/config.py | stdlib (os, threading, pathlib, yaml) |
| services/infrastructure/ai_adapter.py | services.infrastructure.config, services.utils.*, services.compliance.caption_policy |
| services/repositories/* | services.infrastructure.database |

### webapp/ (Web Interface)
| Module | Dependencies |
|--------|-------------|
| webapp/server.py | services.infrastructure.config, services.infrastructure.database, services.repositories.*, services.infrastructure.sidecar_adapter, services.core.storage_service, services.utils.*, services.models.*, services.compliance, services.infrastructure.logging |

### External System Dependencies
| External System | Used By | Purpose |
|----------------|---------|---------|
| TiktokAutoUploader | services.infrastructure.tiktok_adapter, scripts/qr_login.py, scripts/import_cookies.py | TikTok upload & cookies |
| FFmpeg | services.infrastructure.ffmpeg_adapter | Video encoding |
| rclone | services.infrastructure.rclone_adapter | Google Drive sync |
| Apify | services.infrastructure.competitor_scraper | Competitor scraping |
| Telegram Bot API | scripts/telegram_bot.py, webapp/server.py | User interface |
| SQLite | services.infrastructure.database | Persistence |
| AI API (OpenAI-compatible) | services.infrastructure.ai_adapter | AI generation |
| Playwright | scripts/qr_login.py | Headless browser login |
| Skia | services.infrastructure.skia_adapter, services.transform.video_transformer | Text rendering |

## Verification: No Cycles Found
- ✅ No scripts/* → services/* → scripts/* cycles
- ✅ No webapp/* → services/* → webapp/* cycles
- ✅ No services/core/* → scripts/* cycles
- ✅ No services/infrastructure/* → scripts/* cycles
- ✅ No domain (compliance/transform) → scripts/* cycles

## Import Pattern Compliance
- All imports use absolute paths from project root
- No `sys.path.insert` hacks in services/ (only in scripts/ for CLI entry)
- Services layer uses proper package imports
- Tests use TESTING=1 env var to bypass config validation