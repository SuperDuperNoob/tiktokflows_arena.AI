"""Database connection utilities (delegates to services.repositories.Database)."""

import sqlite3
from pathlib import Path
from typing import Optional

from services.utils.paths import db_path


# Schema definitions for analytics tables (kept here for migrations)
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

# Raw stock ledger schema
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


def get_conn(db_path_: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path_) if db_path_ else db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


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


def mark_raw_consumed(product: str, filename: str, file_hash: str | None = None) -> None:
    """Record that a raw video has been consumed (burned + archived for a post)."""
    from services.utils.timezone import utcnow
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
    """Raw raws marked consumed whose Drive copy hasn't been deleted yet."""
    conn = get_conn()
    ensure_ledger(conn)
    rows = conn.execute(
        "SELECT product_name, filename FROM raw_stock "
        "WHERE posted_at IS NOT NULL AND drive_cleaned_at IS NULL").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_drive_cleaned(product: str, filename: str) -> None:
    from services.utils.timezone import utcnow
    conn = get_conn()
    ensure_ledger(conn)
    conn.execute(
        "UPDATE raw_stock SET drive_cleaned_at = ? WHERE product_name = ? AND filename = ?",
        (utcnow(), product, filename))
    conn.commit()
    conn.close()