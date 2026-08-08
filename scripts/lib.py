"""
lib.py - shared helpers for the unified tiktok-machine pipeline.

Port of the battle-tested tiktokflow_vps/scripts/tiktokflow_lib.py, adapted to
tiktok-machine's config.yaml-driven layout while keeping the production
lessons that lived there:

  - Business timezone (Asia/Kuala_Lumpur, MYT, UTC+8). "Today" rolls over at
    Malaysian midnight, not UTC, so reports and the daily AI budget line up
    with the shop.
  - Single source of truth for the analytics schema, the stock scan and the
    quality floors (MIN_MB_PER_SEC / MIN_OUTPUT_FRAMES).
  - Proxy shorthand parsing + masked logging + the pre-upload exit-IP geo
    check, so a dead/wrong-country proxy never burns a full metered upload.

Nothing here talks to the network. Import-safe and cheap.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

try:
    from zoneinfo import ZoneInfo
except ImportError:  # py < 3.9
    ZoneInfo = None  # type: ignore[assignment]

# Use centralized config module
from config import get_config as _get_config, cfg as _cfg, reload_config as _reload_config

# Import from utility modules
import sys
import os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from services.utils import paths, timezone, quality, stock, burn_log, queue, db_utils

# Re-export commonly used constants and functions for backward compatibility
PROJECT_ROOT = paths.PROJECT_ROOT
CONFIG_PATH = _get_config().config_path

NON_PRODUCT_DIRS = paths.NON_PRODUCT_DIRS
VIDEO_EXTS = paths.VIDEO_EXTS
TELEGRAM_LIMIT = quality.TELEGRAM_LIMIT

# Config functions
load_config = lambda: _get_config()._data
config = lambda: _get_config()._data
cfg = lambda *p, default=None: _cfg(*p, default=default)
reload_config = lambda: _reload_config()._data

# Path functions - delegate to paths module
env_path = paths.env_path
_resolve = paths._resolve
drive_root = paths.drive_root
processed_dir = paths.processed_dir
failed_dir = paths.failed_dir
posted_dir = paths.posted_dir
sounds_dir = paths.sounds_dir
queue_dir = paths.queue_dir
db_path = paths.db_path
preset_txt = paths.preset_txt
product_txt = paths.product_txt
burn_jsonl = paths.burn_jsonl
deleted_log = paths.deleted_log
success_log = paths.success_log
failed_log = paths.failed_log
growth_report = paths.growth_report
drive_cleanup_log = paths.drive_cleanup_log
daily_report = paths.daily_report

# Timezone functions - delegate to timezone module
TIMEZONE = timezone.TIMEZONE
OWN_HANDLE = timezone.OWN_HANDLE
RIVAL_HANDLE = timezone.RIVAL_HANDLE
local_tz = timezone.local_tz
local_now = timezone.local_now
local_today = timezone.local_today
utcnow = timezone.utcnow
stamp = timezone.stamp
human = timezone.human
clamp_telegram = quality.clamp_telegram

# Database functions - delegate to db_utils module
SCHEMA = db_utils.SCHEMA
get_conn = db_utils.get_conn

RAW_LEDGER_SCHEMA = db_utils.RAW_LEDGER_SCHEMA
ensure_ledger = db_utils.ensure_ledger
mark_raw_consumed = db_utils.mark_raw_consumed
consumed_pending_cleanup = db_utils.consumed_pending_cleanup
mark_drive_cleaned = db_utils.mark_drive_cleaned
ensure_schema = db_utils.ensure_schema

# Quality constants
MIN_MB_PER_SEC = quality.MIN_MB_PER_SEC
MIN_OUTPUT_FRAMES = quality.MIN_OUTPUT_FRAMES

# Stock functions - delegate to stock module
scan_stock = stock.scan_stock

# Burn log functions - delegate to burn_log module
recent_burns = burn_log.recent_burns
quality_check = burn_log.quality_check

# Queue functions - delegate to queue module
queue_count = queue.queue_count

# Proxy functions (kept in lib.py as they're specific to proxy handling)
def normalize_proxy_url(raw: str) -> str:
    """Normalize proxy URL to standard format."""
    if not raw:
        return ""
    s = raw.strip().strip('"').strip("'").strip()
    if not s:
        return ""
    if "://" in s:
        return s
    if "@" in s and ":" in s:
        return f"http://{s}"
    
    from urllib.parse import quote as _quote
    
    def _host_like(field: str) -> bool:
        return ("." in field) or field.replace(".", "").isdigit()
    
    parts = s.split(":")
    if len(parts) == 4:
        a_like = _host_like(parts[2]) and parts[3].isdigit()
        b_like = _host_like(parts[0]) and parts[1].isdigit()
        if b_like and not a_like:
            host, port, user, pwd = parts[0], parts[1], parts[2], parts[3]
        elif a_like and not b_like:
            user, pwd, host, port = parts[0], parts[1], parts[2], parts[3]
        elif parts[1].isdigit() and not parts[3].isdigit():
            host, port, user, pwd = parts[0], parts[1], parts[2], parts[3]
        else:
            user, pwd, host, port = parts[0], parts[1], parts[2], parts[3]
        return f"http://{_quote(user, safe='')}:{_quote(pwd, safe='')}@{host}:{port}"
    if len(parts) == 2 and parts[1].isdigit():
        return f"http://{parts[0]}:{parts[1]}"
    return f"http://{s}"


def mask_proxy(url: str) -> Optional[str]:
    """Mask proxy URL for logging."""
    if not url:
        return None
    try:
        # Handle shorthand format: user:pass@host:port
        if "@" in url and "://" not in url:
            # Shorthand format: user:pass@host:port or host:port:user:pass
            parts = url.split("@")
            if len(parts) == 2:
                creds = parts[0]
                host_port = parts[1]
                if ":" in creds:
                    user, pwd = creds.split(":", 1)
                    user_masked = f"{user[:3]}***@" if len(user) > 3 else "***@"
                else:
                    user_masked = "***@"
                return f"http://{user_masked}{host_port}"
        
        norm = normalize_proxy_url(url)
        from urllib.parse import urlparse
        p = urlparse(norm if "://" in norm else f"http://{norm}")
        user = ""
        try:
            if p.username:
                u = p.username
                user = f"{u[:3]}***@" if len(u) > 3 else "***@"
        except Exception:
            user = "***@"
        try:
            host = p.hostname or "?"
        except Exception:
            host = "?"
        try:
            port = f":{p.port}" if p.port else ""
        except (ValueError, Exception):
            port = ":?"
        except Exception:
            port = ""
        scheme = p.scheme or "http"
        return f"{scheme}://{user}{host}{port}"
    except Exception:
        return "(could not parse TIKTOK_PROXY URL)"


def check_proxy_exit(proxy_url: str, timeout: int = 10) -> tuple[Optional[bool], str]:
    """Verify proxy exits in Malaysia on residential/mobile line."""
    import requests
    proxies = {"http": proxy_url, "https": proxy_url}
    last_err = "no geo endpoint tried"
    try:
        r = requests.get(
            "http://ip-api.com/json/?fields=status,message,country,countryCode,city,isp,org,mobile,proxy,hosting,query",
            proxies=proxies, timeout=timeout)
        j = r.json()
        if j.get("status") == "success":
            cc = j.get("countryCode", "?")
            kinds = []
            if j.get("mobile"):
                kinds.append("mobile/4G")
            if j.get("hosting"):
                kinds.append("DATACENTER-hosting")
            if j.get("proxy"):
                kinds.append("proxy-flagged")
            if not kinds:
                kinds.append("residential/ISP")
            detail = (f"exit_ip={j.get('query')} geo={j.get('city', '?')},{cc} "
                      f"isp={j.get('isp', '?')} org={j.get('org', '?')} "
                      f"type={'+'.join(kinds)}")
            ok = (cc == "MY") and not j.get("hosting")
            return ok, detail
        last_err = f"ip-api: {j.get('message', 'unknown error')}"
    except Exception as e:
        last_err = f"ip-api: {e}"
    try:
        r = requests.get("https://ipinfo.io/json", proxies=proxies, timeout=timeout)
        j = r.json()
        if j.get("ip"):
            cc = j.get("country", "?")
            detail = (f"exit_ip={j.get('ip')} geo={j.get('city', '?')},{cc} "
                      f"org={j.get('org', '?')} type=unknown(ip-api fallback)")
            return (cc == "MY"), detail
        last_err = f"{last_err}; ipinfo: no ip in response"
    except Exception as e:
        last_err = f"{last_err}; ipinfo: {e}"
    return None, f"geo check failed: {last_err}"


def is_proxy_transport_error(exc: Exception) -> bool:
    """Check if exception is a proxy transport error."""
    try:
        import requests
        if isinstance(exc, (requests.exceptions.ProxyError,
                            requests.exceptions.ConnectTimeout)):
            return True
    except Exception:
        pass
    msg = str(exc).lower()
    return any(s in msg for s in (
        "proxyerror",
        "cannot connect to proxy",
        "unable to connect to proxy",
        "tunnel connection failed",
        "407 proxy authentication required",
    ))


# Backward compatibility functions
def load_config() -> dict:
    """Read config.yaml. Delegates to centralized config."""
    return _get_config()._data


def reload_config() -> dict:
    """Force reload of configuration from file."""
    return _reload_config()._data


def env_flag(name: str, default: bool = False) -> bool:
    """Read environment variable as boolean flag."""
    val = os.environ.get(name, "").strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default


def posts_per_day(conn, days: int) -> list[tuple[str, int]]:
    """Get posts per day for the last N days."""
    from datetime import date, timedelta
    today = date.today()
    since = (today - timedelta(days=days)).isoformat()
    query = """
        SELECT substr(posted_at, 1, 10) as day, COUNT(*) as cnt
        FROM videos
        WHERE substr(posted_at, 1, 10) >= ?
        GROUP BY day
        ORDER BY day DESC
    """
    rows = conn.execute(query, (since,)).fetchall()
    return [(row["day"], row["cnt"]) for row in rows]


def recent_posts(conn, days: int) -> list[dict]:
    """Get recent posts with metrics for the last N days."""
    from datetime import date, timedelta
    today = date.today()
    since = (today - timedelta(days=days)).isoformat()
    query = """
        WITH latest AS (
            SELECT video_id, views, likes, shares, comments, snap_date,
                   ROW_NUMBER() OVER (
                       PARTITION BY video_id ORDER BY snap_date DESC
                   ) AS rn
            FROM daily_metrics
        )
        SELECT v.video_id,
               COALESCE(NULLIF(v.product_folder, ''), '(unassigned)') AS product_folder,
               v.caption,
               v.sound_name,
               substr(v.posted_at, 1, 10) AS posted_day,
               COALESCE(l.views, 0) AS views,
               COALESCE(l.likes, 0) AS likes,
               COALESCE(l.shares, 0) AS shares,
               COALESCE(l.comments, 0) AS comments,
               COALESCE(l.likes, 0) + COALESCE(l.shares, 0) + COALESCE(l.comments, 0) AS interactions,
               l.snap_date AS last_snap
        FROM videos v
        LEFT JOIN latest l ON l.video_id = v.video_id AND l.rn = 1
        WHERE substr(v.posted_at, 1, 10) >= ?
        ORDER BY views DESC, v.posted_at DESC
    """
    rows = conn.execute(query, (since,)).fetchall()
    return [dict(row) for row in rows]


def views_delta(conn, days: int) -> int:
    """Get views delta over specified days."""
    from datetime import date, timedelta
    today = date.today().isoformat()
    prior = (date.today() - timedelta(days=days)).isoformat()
    query = """
        WITH snap AS (
            SELECT video_id, views,
                   ROW_NUMBER() OVER (PARTITION BY video_id ORDER BY snap_date DESC) rn
            FROM daily_metrics WHERE snap_date <= ?
        ), older AS (
            SELECT video_id, views,
                   ROW_NUMBER() OVER (PARTITION BY video_id ORDER BY snap_date DESC) rn
            FROM daily_metrics WHERE snap_date <= ?
        )
        SELECT COALESCE(SUM(s.views), 0) - COALESCE(SUM(o.views), 0) AS delta
        FROM snap s LEFT JOIN older o ON o.video_id = s.video_id AND o.rn = 1
        WHERE s.rn = 1
    """
    row = conn.execute(query, (today, prior)).fetchone()
    return int(row["delta"] or 0) if row else 0


# Type hints for Optional
from typing import Optional