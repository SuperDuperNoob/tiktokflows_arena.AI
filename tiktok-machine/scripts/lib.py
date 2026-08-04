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


# ----------------------------------------------------------------- config ----

def _default_home() -> str:
    env_h = os.environ.get("TIKTOKFLOW_HOME") or os.environ.get("TIKTOK_MACHINE_HOME")
    if env_h:
        return os.path.expanduser(env_h)
    this_dir = Path(__file__).resolve().parent
    if this_dir.name == "scripts":
        return str(this_dir.parent)
    return str(this_dir)


PROJECT_ROOT = Path(_default_home())
CONFIG_PATH = Path(os.environ.get(
    "TIKTOK_MACHINE_CONFIG",
    str(PROJECT_ROOT / "config" / "config.yaml")))

# Directories under the drive root that are never products.
NON_PRODUCT_DIRS = {
    "soundtrack", "processed", "posted", "failed", "tmp", "VideosDirPath",
    "burn_output", "test_folder", "logs", "archive", "Books",
    "captions", "sounds", "content",
}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}

# Telegram hard-caps a message at 4096 chars.
TELEGRAM_LIMIT = 3900


def load_config() -> dict:
    """Read config.yaml. Missing file -> empty dict (everything has defaults)."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml_safe_load(f)
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def yaml_safe_load(text) -> dict:
    try:
        import yaml
        return yaml.safe_load(text) or {}
    except Exception:
        return {}


_CFG: dict | None = None


def config() -> dict:
    """Load config.yaml once and cache it."""
    global _CFG
    if _CFG is None:
        _CFG = load_config()
    return _CFG


def cfg(*path: str, default=None):
    """Drill into the config dict. `cfg('proxy','strict_mode')`."""
    node: dict = config()
    for key in path:
        if not isinstance(node, dict):
            return default
        node = node.get(key)
    return node if node is not None else default


# ---------------------------------------------------------------- paths ----

def env_path(var: str, default: str) -> Path:
    return Path(os.path.expanduser(os.environ.get(var) or default))


def _resolve(p: str) -> Path:
    p = os.path.expanduser(p or "")
    if not p:
        return PROJECT_ROOT
    if not os.path.isabs(p):
        return PROJECT_ROOT / p
    return Path(p)


def drive_root() -> Path:
    """Root where product video folders live (content/raw in this layout)."""
    return _resolve(cfg("content", "raw_dir",
                        default=str(PROJECT_ROOT / "content" / "raw")))


def processed_dir() -> Path:
    return _resolve(cfg("content", "processed_dir",
                        default=str(PROJECT_ROOT / "content" / "processed")))


def failed_dir() -> Path:
    return _resolve(cfg("content", "failed_dir",
                        default=str(PROJECT_ROOT / "content" / "failed")))


def posted_dir() -> Path:
    return _resolve(cfg("content", "posted_dir",
                        default=str(PROJECT_ROOT / "content" / "posted")))


def sounds_dir() -> Path:
    return _resolve(cfg("content", "sounds_dir",
                        default=str(PROJECT_ROOT / "sounds")))


def queue_dir() -> Path:
    """Rendered videos waiting for the uploader. This is the real queue."""
    return _resolve(cfg("content", "queue_dir",
                        default=str(PROJECT_ROOT / "content" / "processed")))


def db_path() -> Path:
    p = cfg("logging", "db_path", default=str(PROJECT_ROOT / "logs" / "tiktok.db"))
    return _resolve(p)


def preset_txt() -> Path:
    return _resolve(cfg("content", "preset_text",
                        default=str(drive_root() / "preset_text.txt")))


def product_txt() -> Path:
    return _resolve(cfg("content", "product_id_file",
                        default=str(drive_root() / "product_id.txt")))


def burn_jsonl() -> Path:
    return _resolve(cfg("content", "burn_log",
                        default=str(PROJECT_ROOT / "logs" / "burn_log.jsonl")))


def deleted_log() -> Path:
    return _resolve(cfg("content", "deleted_log",
                        default=str(PROJECT_ROOT / "logs" / "deleted.log")))


def success_log() -> Path:
    return _resolve(cfg("content", "success_log",
                        default=str(PROJECT_ROOT / "logs" / "success.log")))


def failed_log() -> Path:
    return _resolve(cfg("content", "failed_log",
                        default=str(PROJECT_ROOT / "logs" / "failed.log")))


def growth_report() -> Path:
    return _resolve(cfg("content", "growth_report",
                        default=str(PROJECT_ROOT / "logs" / "growth_report.txt")))


def drive_cleanup_log() -> Path:
    """Audit of remote files deleted by sync_out (review only, not load-bearing)."""
    return _resolve(cfg("content", "drive_cleanup_log",
                        default=str(PROJECT_ROOT / "logs" / "drive_cleanup.log")))


def daily_report() -> Path:
    return _resolve(cfg("content", "daily_report",
                        default=str(PROJECT_ROOT / "logs" / "daily_report.txt")))


# ------------------------------------------------------------ timezone ----

TIMEZONE = os.environ.get("TIKTOKFLOW_TZ") or \
    cfg("timezone", "tz", default="Asia/Kuala_Lumpur") or "Asia/Kuala_Lumpur"

OWN_HANDLE = (os.environ.get("TIKTOK_SESSION_USER")
              or cfg("tiktok", "session_username") or "kumpul.shop").lower()
RIVAL_HANDLE = (os.environ.get("TIKTOK_RIVAL_HANDLE")
                or cfg("analytics", "rival_handle")
                or "reski.reski700").lower()


def local_tz():
    if ZoneInfo is None:
        return None
    try:
        return ZoneInfo(TIMEZONE)
    except Exception:
        return None


def local_now() -> datetime:
    return datetime.now(local_tz())


def local_today() -> date:
    return local_now().date()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def stamp(dt: datetime | None = None) -> str:
    dt = dt or local_now()
    label = TIMEZONE if dt.tzinfo else f"{TIMEZONE}?"
    return f"{dt.strftime('%Y-%m-%d %H:%M')} {label}"


def human(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return "0"


def clamp_telegram(text: str, limit: int = TELEGRAM_LIMIT) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    nl = cut.rfind("\n")
    if nl > limit * 0.6:
        cut = cut[:nl]
    return cut.rstrip() + "\n… (truncated)"


# ------------------------------------------------------------------ db ----

# Mirrors tiktokflow_lib.SCHEMA. `videos`, `daily_metrics`,
# `competitor_videos`, `competitor_daily`, `daily_summary` live in the SAME
# sqlite file as db.py's operational tables (posts / raw_stock / ...).
SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    video_id        TEXT PRIMARY KEY,
    product_folder  TEXT,
    caption         TEXT,
    hashtags_json   TEXT,
    sound_id        TEXT,
    sound_name      TEXT,
    posted_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_videos_product ON videos(product_folder);
CREATE INDEX IF NOT EXISTS idx_videos_posted  ON videos(posted_at);

CREATE TABLE IF NOT EXISTS daily_metrics (
    video_id    TEXT NOT NULL,
    snap_date   TEXT NOT NULL,
    views       INTEGER DEFAULT 0,
    likes       INTEGER DEFAULT 0,
    shares      INTEGER DEFAULT 0,
    saves       INTEGER DEFAULT 0,
    comments    INTEGER DEFAULT 0,
    captured_at TEXT NOT NULL,
    PRIMARY KEY (video_id, snap_date),
    FOREIGN KEY (video_id) REFERENCES videos(video_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_metrics_date ON daily_metrics(snap_date);

CREATE TABLE IF NOT EXISTS competitor_videos (
    video_id        TEXT NOT NULL,
    handle          TEXT NOT NULL,
    caption         TEXT,
    hashtags_json   TEXT,
    sound_id        TEXT,
    sound_name      TEXT,
    sound_author    TEXT,
    views           INTEGER DEFAULT 0,
    likes           INTEGER DEFAULT 0,
    shares          INTEGER DEFAULT 0,
    comments        INTEGER DEFAULT 0,
    posted_at       TEXT,
    snap_date       TEXT NOT NULL,
    captured_at     TEXT NOT NULL,
    PRIMARY KEY (video_id, snap_date)
);
CREATE INDEX IF NOT EXISTS idx_cv_handle ON competitor_videos(handle);
CREATE INDEX IF NOT EXISTS idx_cv_snap   ON competitor_videos(snap_date);
CREATE INDEX IF NOT EXISTS idx_cv_views  ON competitor_videos(views DESC);
CREATE INDEX IF NOT EXISTS idx_cv_handle_snap ON competitor_videos(handle, snap_date);

CREATE TABLE IF NOT EXISTS competitor_daily (
    handle          TEXT NOT NULL,
    snap_date       TEXT NOT NULL,
    followers       INTEGER,
    posts_today     INTEGER,
    top_sound_id    TEXT,
    top_sound_name  TEXT,
    top_hashtag     TEXT,
    top_views       INTEGER,
    captured_at     TEXT NOT NULL,
    PRIMARY KEY (handle, snap_date)
);

CREATE TABLE IF NOT EXISTS daily_summary (
    snap_date       TEXT PRIMARY KEY,
    best_product    TEXT,
    best_sound_id   TEXT,
    best_sound_name TEXT,
    best_hashtag    TEXT,
    total_views     INTEGER,
    total_uploads   INTEGER,
    competitor_gap  INTEGER,
    notes           TEXT,
    ai_called_at    TEXT
);
"""


def get_conn(db_path_: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path_) if db_path_ else db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ------------------------------------------------------------------ ledger ----
# "Already consumed for a post" is recorded HERE (in SQLite) instead of in a
# deleted.log file. This is the source of truth for whether a raw video has
# been posted. The Drive deletefile (sync_out) is then just COSMETIC cleanup —
# even if it fails, the DB still knows the raw was posted and never re-selects
# it, so a missed delete can never cause a duplicate upload.

RAW_LEDGER_SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_stock (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT NOT NULL,
    filename TEXT NOT NULL,
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_used DATETIME,
    use_count INTEGER DEFAULT 0,
    file_hash TEXT,
    posted_at TEXT,
    drive_cleaned_at TEXT,
    UNIQUE(product_name, filename)
);
"""


def ensure_ledger(conn: sqlite3.Connection) -> None:
    """Create raw_stock (with ledger columns) and migrate older tables. Idempotent."""
    conn.execute(RAW_LEDGER_SCHEMA)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(raw_stock)")}
    if "file_hash" not in cols:
        conn.execute("ALTER TABLE raw_stock ADD COLUMN file_hash TEXT")
    if "posted_at" not in cols:
        conn.execute("ALTER TABLE raw_stock ADD COLUMN posted_at TEXT")
    if "drive_cleaned_at" not in cols:
        conn.execute("ALTER TABLE raw_stock ADD COLUMN drive_cleaned_at TEXT")
    conn.commit()


def mark_raw_consumed(product: str, filename: str, file_hash: str | None = None) -> None:
    """Record that a raw video has been consumed (burned + archived for a post).

    This is the SINGLE place that marks a raw as "done". Once set, no selector
    will ever pick it again, and sync_out will try to delete it from Drive.
    Idempotent — safe to call more than once for the same raw.
    """
    conn = get_conn()
    ensure_ledger(conn)
    conn.execute("INSERT OR IGNORE INTO raw_stock(product_name, filename) VALUES (?, ?)",
                 (product, filename))
    conn.execute(
        "UPDATE raw_stock SET file_hash = COALESCE(?, file_hash), "
        "posted_at = COALESCE(posted_at, ?) WHERE product_name = ? AND filename = ?",
        (file_hash, utcnow(), product, filename))
    conn.commit()
    conn.close()


def consumed_pending_cleanup() -> list[dict]:
    """Raw raws marked consumed whose Drive copy hasn't been deleted yet.

    These are the deletefile targets for sync_out. Missing a delete is safe:
    they stay here to be retried, and they're excluded from selection anyway.
    """
    conn = get_conn()
    ensure_ledger(conn)
    rows = conn.execute(
        "SELECT product_name, filename FROM raw_stock "
        "WHERE posted_at IS NOT NULL AND drive_cleaned_at IS NULL").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_drive_cleaned(product: str, filename: str) -> None:
    conn = get_conn()
    ensure_ledger(conn)
    conn.execute(
        "UPDATE raw_stock SET drive_cleaned_at = ? WHERE product_name = ? AND filename = ?",
        (utcnow(), product, filename))
    conn.commit()
    conn.close()


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create analytics tables + additive migrations. Idempotent."""
    conn.executescript(SCHEMA)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(videos)")}
    if "tiktok_video_id" not in cols:
        conn.execute("ALTER TABLE videos ADD COLUMN tiktok_video_id TEXT")
    if "matched_at" not in cols:
        conn.execute("ALTER TABLE videos ADD COLUMN matched_at TEXT")
    sum_cols = {r["name"] for r in conn.execute("PRAGMA table_info(daily_summary)")}
    if "ai_called_at" not in sum_cols:
        conn.execute("ALTER TABLE daily_summary ADD COLUMN ai_called_at TEXT")
    ensure_ledger(conn)
    conn.commit()


# --------------------------------------------------------------- quality ----

# A burn below this MB/s is a quality regression. Mirrors process-videos-v4.sh.
MIN_MB_PER_SEC = float(os.environ.get("MIN_MB_PER_SEC") or
                       cfg("encoding", "min_mb_per_sec", default=0.30) or 0.30)
# Fewer frames than this => the burn is a still image, not a video.
MIN_OUTPUT_FRAMES = int(os.environ.get("MIN_OUTPUT_FRAMES") or
                        cfg("encoding", "min_output_frames", default=10) or 10)


def scan_stock(root: Path | None = None) -> dict[str, int]:
    """{product_folder: count of raw video files}. One definition, everywhere."""
    root = Path(root) if root else drive_root()
    stock: dict[str, int] = {}
    if not root.exists():
        return stock
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if entry.name in NON_PRODUCT_DIRS:
            continue
        try:
            stock[entry.name] = sum(
                1 for f in entry.iterdir()
                if f.is_file() and f.suffix.lower() in VIDEO_EXTS
            )
        except OSError:
            continue
    return stock


def recent_burns(limit: int = 20, burn_path: Path | None = None) -> list[dict]:
    path = Path(burn_path) if burn_path else burn_jsonl()
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def quality_check(limit: int = 10, burn_path: Path | None = None) -> dict | None:
    burns = [b for b in recent_burns(limit, burn_path) if b.get("mb_per_sec")]
    if not burns:
        return None
    rates = [float(b["mb_per_sec"]) for b in burns]
    latest = burns[-1]
    bad = [b for b in burns if b.get("low_quality")]
    enc = latest.get("encode") or {}
    frames = latest.get("frames")
    stills = [b for b in burns
              if b.get("frames") is not None and 0 < b["frames"] < MIN_OUTPUT_FRAMES]
    return {
        "count": len(burns),
        "latest_mb_per_sec": float(latest["mb_per_sec"]),
        "latest_kbps": int(latest.get("video_kbps") or 0),
        "avg_mb_per_sec": sum(rates) / len(rates),
        "min_mb_per_sec": min(rates),
        "low_count": len(bad),
        "crf": enc.get("crf"),
        "maxrate": enc.get("maxrate"),
        "degraded": bool(latest.get("low_quality")),
        "frames": frames,
        "duration_s": latest.get("duration_s"),
        "is_still": (None if frames is None
                     else bool(frames and frames < MIN_OUTPUT_FRAMES)),
        "still_count": len(stills),
    }


def queue_count(root: Path | None = None) -> int:
    """Rendered mp4s in the queue that carry a sidecar."""
    root = Path(root) if root else queue_dir()
    if not root.exists():
        return 0
    n = 0
    try:
        for f in root.glob("*.mp4"):
            if f.with_suffix(".json").exists() or f.with_suffix(".pid").exists():
                n += 1
    except OSError:
        return 0
    return n


# --------------------------------------------------------- performance ----

def recent_posts(conn: sqlite3.Connection, days: int = 3) -> list[dict]:
    since = (local_today() - timedelta(days=days)).isoformat()
    rows = conn.execute(
        """
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
               substr(v.posted_at, 1, 10)        AS posted_day,
               COALESCE(l.views, 0)              AS views,
               COALESCE(l.likes, 0)              AS likes,
               COALESCE(l.shares, 0)             AS shares,
               COALESCE(l.comments, 0)           AS comments,
               COALESCE(l.likes, 0) + COALESCE(l.shares, 0)
                   + COALESCE(l.comments, 0)     AS interactions,
               l.snap_date                       AS last_snap
        FROM videos v
        LEFT JOIN latest l ON l.video_id = v.video_id AND l.rn = 1
        WHERE substr(v.posted_at, 1, 10) >= ?
        ORDER BY views DESC, v.posted_at DESC
        """,
        (since,),
    ).fetchall()
    return [dict(r) for r in rows]


def posts_per_day(conn: sqlite3.Connection, days: int = 3) -> list[tuple[str, int]]:
    since = (local_today() - timedelta(days=days)).isoformat()
    rows = conn.execute(
        """
        SELECT substr(posted_at, 1, 10) AS day, COUNT(*) AS n
        FROM videos
        WHERE substr(posted_at, 1, 10) >= ?
        GROUP BY day ORDER BY day DESC
        """,
        (since,),
    ).fetchall()
    return [(r["day"], r["n"]) for r in rows]


def own_performance(conn: sqlite3.Connection, days: int = 7) -> list[dict]:
    since = (local_today() - timedelta(days=days)).isoformat()
    try:
        rows = conn.execute(
            """
            WITH latest AS (
                SELECT video_id, views, likes, shares, comments, snap_date,
                       ROW_NUMBER() OVER (
                           PARTITION BY video_id ORDER BY snap_date DESC
                       ) AS rn
                FROM daily_metrics
                WHERE snap_date >= ?
            )
            SELECT
                COALESCE(NULLIF(v.product_folder, ''), '(unassigned)') AS product_folder,
                COUNT(*)                       AS uploads,
                CAST(SUM(l.views)  AS INTEGER) AS sum_views,
                CAST(AVG(l.views)  AS INTEGER) AS avg_views,
                MAX(l.views)                   AS best_views,
                CAST(SUM(l.likes)  AS INTEGER) AS sum_likes,
                ROUND(100.0 * SUM(l.likes) / NULLIF(SUM(l.views), 0), 2) AS engage_pct
            FROM latest l
            JOIN videos v ON v.video_id = l.video_id
            WHERE l.rn = 1
            GROUP BY product_folder
            ORDER BY avg_views DESC
            """,
            (since,),
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        # Older SQLite without window functions: fallback per-video MAX.
        rows = conn.execute(
            """
            SELECT COALESCE(NULLIF(v.product_folder,''),'(unassigned)') AS product_folder,
                   COUNT(*) AS uploads,
                   CAST(SUM(m.views) AS INTEGER) AS sum_views,
                   CAST(AVG(m.views) AS INTEGER) AS avg_views,
                   MAX(m.views) AS best_views,
                   CAST(SUM(m.likes) AS INTEGER) AS sum_likes,
                   ROUND(100.0*SUM(m.likes)/NULLIF(SUM(m.views),0),2) AS engage_pct
            FROM daily_metrics m
            JOIN videos v ON v.video_id = m.video_id
            JOIN (SELECT video_id, MAX(snap_date) ms FROM daily_metrics
                  WHERE snap_date >= ? GROUP BY video_id) t
              ON t.video_id = m.video_id AND t.ms = m.snap_date
            GROUP BY product_folder ORDER BY avg_views DESC
            """, (since,)).fetchall()
        return [dict(r) for r in rows]


def views_delta(conn: sqlite3.Connection, days: int = 1) -> int:
    today = local_today().isoformat()
    prior = (local_today() - timedelta(days=days)).isoformat()
    row = conn.execute(
        """
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
        """,
        (today, prior),
    ).fetchone()
    return int(row["delta"] or 0) if row else 0


def latest_handle_snapshot(conn: sqlite3.Connection, handle: str) -> dict | None:
    row = conn.execute(
        """
        SELECT handle, snap_date, followers, posts_today,
               top_sound_name, top_hashtag, top_views
        FROM competitor_daily
        WHERE handle = ?
        ORDER BY snap_date DESC LIMIT 1
        """,
        (handle.lower(),),
    ).fetchone()
    return dict(row) if row else None


def rival_gap(conn: sqlite3.Connection) -> dict | None:
    own = latest_handle_snapshot(conn, OWN_HANDLE)
    rival = latest_handle_snapshot(conn, RIVAL_HANDLE)
    if not own or not rival:
        return None
    own_v = own.get("top_views") or 0
    rival_v = rival.get("top_views") or 0
    return {
        "own_handle": OWN_HANDLE,
        "rival_handle": RIVAL_HANDLE,
        "own_views": own_v,
        "rival_views": rival_v,
        "gap": rival_v - own_v,
        "behind": rival_v > own_v,
        "own_date": own.get("snap_date"),
        "rival_date": rival.get("snap_date"),
        "stale": own.get("snap_date") != local_today().isoformat(),
    }


# ---------------------------------------------------------------- proxy ----

def env_flag(name: str, default: bool = False) -> bool:
    v = os.environ.get(name, "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "on")


def normalize_proxy_url(raw: str) -> str:
    """Accept many vendor formats and return a requests-ready proxy URL.

    Supported inputs:
      - http://user:pass@host:port   (canonical, returned as-is)
      - socks5://user:pass@host:port (kept as-is)
      - user:pass@host:port          -> http://user:pass@host:port
      - user:passwd:host:port        -> http://user:passwd@host:port
      - host:port:user:passwd        -> http://user:passwd@host:port
      - host:port                    -> http://host:port
    User/pass are URL-encoded to survive special chars.
    """
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
        # IP (all digits+dots) or a dotted hostname. Bare hostnames are
        # ambiguous, so they only win via the port-position tiebreaker below.
        return ("." in field) or field.replace(".", "").isdigit()

    parts = s.split(":")
    if len(parts) == 4:
        # Two plausible readings:
        #   A) user:passwd:host:port    (parts[2]=host, parts[3]=port)
        #   B) host:port:user:passwd    (parts[0]=host, parts[1]=port)
        # Disambiguate on host-likeness first, then fall back to the numeric
        # port position (a port is always numeric; a password usually is not).
        a_like = _host_like(parts[2]) and parts[3].isdigit()
        b_like = _host_like(parts[0]) and parts[1].isdigit()
        if b_like and not a_like:
            host, port, user, pwd = parts[0], parts[1], parts[2], parts[3]
        elif a_like and not b_like:
            user, pwd, host, port = parts[0], parts[1], parts[2], parts[3]
        elif parts[1].isdigit() and not parts[3].isdigit():
            # Only index 1 is a port -> host:port:user:passwd (vendor B)
            host, port, user, pwd = parts[0], parts[1], parts[2], parts[3]
        else:
            # Ambiguous or index 3 is the port -> default user:pass:host:port
            user, pwd, host, port = parts[0], parts[1], parts[2], parts[3]
        return f"http://{_quote(user, safe='')}:{_quote(pwd, safe='')}@{host}:{port}"
    if len(parts) == 2 and parts[1].isdigit():
        return f"http://{parts[0]}:{parts[1]}"
    return f"http://{s}"


def mask_proxy(url: str) -> str | None:
    """Log-safe proxy rendering: scheme://use***@host:port - never the password."""
    if not url:
        return None
    try:
        norm = normalize_proxy_url(url)
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
        except ValueError:
            port = ":?"
        except Exception:
            port = ""
        scheme = p.scheme or "http"
        return f"{scheme}://{user}{host}{port}"
    except Exception:
        return "(could not parse TIKTOK_PROXY URL)"


def check_proxy_exit(proxy_url: str, timeout: int = 10):
    """Verify the proxy exits in Malaysia on a residential/mobile line.

    Costs ~2KB of proxy traffic and runs BEFORE any video bytes are sent.

    Returns (ok, detail): True = verified MY residential/mobile;
    False = verified bad (non-MY or hosting); None = check unreachable.
    """
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
    """True for 'the proxy itself is broken' errors (NOT TikTok API errors)."""
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
