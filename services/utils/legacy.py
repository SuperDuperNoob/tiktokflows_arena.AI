"""Legacy compatibility module - consolidates all lib.py functionality.

This module replaces lib.py by consolidating all its functionality
into the appropriate utility modules. Services should import from
the specific utility modules instead of this legacy module.

This module exists only as a compatibility layer for scripts that
haven't been migrated yet.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

try:
    from zoneinfo import ZoneInfo
except ImportError:  # py < 3.9
    ZoneInfo = None  # type: ignore[assignment]

# Re-export from utility modules
from services.utils.paths import (
    PROJECT_ROOT,
    NON_PRODUCT_DIRS,
    VIDEO_EXTS,
    env_path,
    _resolve,
    drive_root,
    processed_dir,
    failed_dir,
    posted_dir,
    sounds_dir,
    queue_dir,
    db_path,
    preset_txt,
    product_txt,
    burn_jsonl,
    deleted_log,
    success_log,
    failed_log,
    growth_report,
    drive_cleanup_log,
    daily_report,
)

from services.utils.timezone import (
    TIMEZONE,
    OWN_HANDLE,
    RIVAL_HANDLE,
    local_tz,
    local_now,
    local_today,
    utcnow,
    stamp,
    human,
    MYT_OFFSET,
    MYT,
)

from services.utils.quality import (
    MIN_MB_PER_SEC,
    MIN_OUTPUT_FRAMES,
    TELEGRAM_LIMIT,
    clamp_telegram,
)

from services.utils.stock import scan_stock
from services.utils.burn_log import recent_burns, quality_check
from services.utils.queue import queue_count
from services.utils.db_utils import (
    SCHEMA,
    RAW_LEDGER_SCHEMA,
    get_conn,
    ensure_ledger,
    ensure_schema,
    mark_raw_consumed,
    consumed_pending_cleanup,
    mark_drive_cleaned,
)

# Config functions - delegated to centralized config
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
from config import get_config as _get_config, cfg as _cfg, reload_config as _reload_config

# Proxy functions
from urllib.parse import quote as _quote

# Constants from lib that aren't in utility modules
TELEGRAM_LIMIT = 3900

# Config functions
def load_config() -> dict:
    """Read config.yaml. Delegates to centralized config."""
    return _get_config()._data


def config() -> dict:
    """Load config.yaml once and cache it. Delegates to centralized config."""
    return _get_config()._data


def cfg(*path: str, default=None):
    """Drill into the config dict. `cfg('proxy','strict_mode')`. Delegates to centralized config."""
    return _cfg(*path, default=default)


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


def md5_file(p: Path, chunk: int = 8192) -> str:
    h = hashlib.md5()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(chunk), b""):
            h.update(chunk)
    return h.hexdigest()


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


# Analytics helper functions
def posts_per_day(conn, days: int) -> list[tuple[str, int]]:
    """Get posts per day for the last N days."""
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


# Type hints
from typing import Optional


# Create a lib-like namespace for backward compatibility
class _LibNamespace:
    """Namespace object that mimics the old lib module."""
    
    PROJECT_ROOT = PROJECT_ROOT
    NON_PRODUCT_DIRS = NON_PRODUCT_DIRS
    VIDEO_EXTS = VIDEO_EXTS
    TELEGRAM_LIMIT = TELEGRAM_LIMIT
    TIMEZONE = TIMEZONE
    OWN_HANDLE = OWN_HANDLE
    RIVAL_HANDLE = RIVAL_HANDLE
    MYT_OFFSET = MYT_OFFSET
    MYT = MYT
    MIN_MB_PER_SEC = MIN_MB_PER_SEC
    MIN_OUTPUT_FRAMES = MIN_OUTPUT_FRAMES
    
    # Functions
    load_config = staticmethod(load_config)
    config = staticmethod(config)
    cfg = staticmethod(cfg)
    reload_config = staticmethod(reload_config)
    env_flag = staticmethod(env_flag)
    md5_file = staticmethod(md5_file)
    normalize_proxy_url = staticmethod(normalize_proxy_url)
    mask_proxy = staticmethod(mask_proxy)
    check_proxy_exit = staticmethod(check_proxy_exit)
    is_proxy_transport_error = staticmethod(is_proxy_transport_error)
    local_tz = staticmethod(local_tz)
    local_now = staticmethod(local_now)
    local_today = staticmethod(local_today)
    utcnow = staticmethod(utcnow)
    stamp = staticmethod(stamp)
    human = staticmethod(human)
    clamp_telegram = staticmethod(clamp_telegram)
    scan_stock = staticmethod(scan_stock)
    recent_burns = staticmethod(recent_burns)
    quality_check = staticmethod(quality_check)
    queue_count = staticmethod(queue_count)
    get_conn = staticmethod(get_conn)
    ensure_ledger = staticmethod(ensure_ledger)
    ensure_schema = staticmethod(ensure_schema)
    mark_raw_consumed = staticmethod(mark_raw_consumed)
    consumed_pending_cleanup = staticmethod(consumed_pending_cleanup)
    mark_drive_cleaned = staticmethod(mark_drive_cleaned)
    posts_per_day = staticmethod(posts_per_day)
    recent_posts = staticmethod(recent_posts)
    views_delta = staticmethod(views_delta)
    
    # Path functions
    env_path = staticmethod(env_path)
    _resolve = staticmethod(_resolve)
    drive_root = staticmethod(drive_root)
    processed_dir = staticmethod(processed_dir)
    failed_dir = staticmethod(failed_dir)
    posted_dir = staticmethod(posted_dir)
    sounds_dir = staticmethod(sounds_dir)
    queue_dir = staticmethod(queue_dir)
    db_path = staticmethod(db_path)
    preset_txt = staticmethod(preset_txt)
    product_txt = staticmethod(product_txt)
    burn_jsonl = staticmethod(burn_jsonl)
    deleted_log = staticmethod(deleted_log)
    success_log = staticmethod(success_log)
    failed_log = staticmethod(failed_log)
    growth_report = staticmethod(growth_report)
    drive_cleanup_log = staticmethod(drive_cleanup_log)
    daily_report = staticmethod(daily_report)
    
    # Schema
    SCHEMA = SCHEMA
    RAW_LEDGER_SCHEMA = RAW_LEDGER_SCHEMA

# Create the lib namespace instance
lib = _LibNamespace()