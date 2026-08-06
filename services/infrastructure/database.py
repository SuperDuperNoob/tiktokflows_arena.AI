"""SQLite database layer for the TikTok Auto-Posting Machine.

Provides a single Database class that initializes the schema and exposes
convenience methods for all tables: posts, raw_stock, caption_pool,
competitor_data, system_events.
"""

import sqlite3
import os
import json
from datetime import datetime, timezone
from typing import Optional
from contextlib import contextmanager


SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT NOT NULL,
    product_id TEXT NOT NULL,
    raw_video_path TEXT NOT NULL,
    processed_video_path TEXT NOT NULL,
    caption_text TEXT NOT NULL,
    description_text TEXT,
    product_tag_text TEXT,
    sound_file TEXT,
    speed_factor REAL,
    brightness_shift REAL,
    posted_at DATETIME,
    status TEXT DEFAULT 'PENDING',  -- PENDING, TRANSFORMING, POSTED, FAILED, RETRY
    tiktok_post_id TEXT,
    views INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    last_analytics_check DATETIME,
    proxy_ip_used TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS raw_stock (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT NOT NULL,
    filename TEXT NOT NULL,
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_used DATETIME,
    use_count INTEGER DEFAULT 0,
    file_hash TEXT,            -- fingerprint of the raw video
    posted_at TEXT,            -- set when the raw is consumed (burned+archived); the source of truth for "already posted"
    drive_cleaned_at TEXT,     -- set when sync_out deleted its Drive copy (cosmetic cleanup)
    UNIQUE(product_name, filename)
);

CREATE TABLE IF NOT EXISTS caption_pool (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT,  -- NULL = generic, usable for any product
    caption_text TEXT NOT NULL,
    description_text TEXT,
    product_tag_text TEXT,
    compliance_checked INTEGER DEFAULT 0,
    times_used INTEGER DEFAULT 0,
    last_used DATETIME,
    source TEXT DEFAULT 'manual',  -- manual, ai_generated, competitor_inspired
    original_text TEXT,  -- if rewritten, stores original
    UNIQUE(product_name, caption_text)
);

CREATE TABLE IF NOT EXISTS competitor_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competitor_handle TEXT NOT NULL,
    post_url TEXT,
    product_keywords TEXT,
    hashtags TEXT,
    sound_used TEXT,
    view_count INTEGER,
    caption_text TEXT,
    scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS system_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT,  -- UPLOAD_SUCCESS, UPLOAD_FAIL, COOKIE_WARNING, STOCK_LOW, PROXY_FAIL, AI_CALL, SCRAPE_COMPLETE
    message TEXT,
    metadata TEXT,  -- JSON blob for extra data
    occurred_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
CREATE INDEX IF NOT EXISTS idx_posts_product ON posts(product_name);
CREATE INDEX IF NOT EXISTS idx_posts_posted_at ON posts(posted_at);
CREATE INDEX IF NOT EXISTS idx_raw_stock_product ON raw_stock(product_name);
CREATE INDEX IF NOT EXISTS idx_raw_stock_last_used ON raw_stock(last_used);
CREATE INDEX IF NOT EXISTS idx_caption_pool_product ON caption_pool(product_name);
CREATE INDEX IF NOT EXISTS idx_caption_pool_compliance ON caption_pool(compliance_checked);
CREATE INDEX IF NOT EXISTS idx_system_events_type ON system_events(event_type);
CREATE INDEX IF NOT EXISTS idx_system_events_occurred ON system_events(occurred_at);
"""


class Database:
    """Thread-safe SQLite database wrapper."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_schema()

    def _init_schema(self):
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            # Migrate older tables
            # raw_stock
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(raw_stock)")}
            for col, ddl in (("file_hash", "TEXT"),
                             ("posted_at", "TEXT"),
                             ("drive_cleaned_at", "TEXT")):
                if col not in cols:
                    conn.execute(f"ALTER TABLE raw_stock ADD COLUMN {col} {ddl}")

            # posts
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(posts)")}
            for col, ddl in (("description_text", "TEXT"),
                             ("product_tag_text", "TEXT"),
                             ("created_at", "TEXT"),
                             ("updated_at", "TEXT"),
                             ("video_hash", "TEXT"),
                             ("source_path", "TEXT"),
                             ("job_uuid", "TEXT"),
                             ("compliance_status", "TEXT"),
                             ("compliance_details", "TEXT"),
                             ("retry_count", "INTEGER DEFAULT 0"),
                             ("max_retries", "INTEGER DEFAULT 3"),
                             ("last_error", "TEXT")):
                if col not in cols:
                    conn.execute(f"ALTER TABLE posts ADD COLUMN {col} {ddl}")

            # caption_pool
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(caption_pool)")}
            for col, ddl in (("description_text", "TEXT"),
                             ("product_tag_text", "TEXT")):
                if col not in cols:
                    conn.execute(f"ALTER TABLE caption_pool ADD COLUMN {col} {ddl}")

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # =========================================================================
    # POSTS
    # =========================================================================

    def create_post(self, product_name: str, product_id: str,
                    raw_video_path: str, processed_video_path: str,
                    caption_text: str, description_text: str = None,
                    product_tag_text: str = None, sound_file: str = None,
                    speed_factor: float = None, brightness_shift: float = None) -> int:
        """Create a new post record. Returns the post ID."""
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO posts
                   (product_name, product_id, raw_video_path, processed_video_path,
                    caption_text, description_text, product_tag_text, sound_file, speed_factor, brightness_shift, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')""",
                (product_name, product_id, raw_video_path, processed_video_path,
                 caption_text, description_text, product_tag_text, sound_file, speed_factor, brightness_shift)
            )
            return cur.lastrowid

    def update_post_status(self, post_id: int, status: str,
                           proxy_ip: str = None, tiktok_post_id: str = None,
                           notes: str = None):
        """Update post status and optional fields."""
        with self._connect() as conn:
            sets = ["status = ?", "posted_at = ?"]
            vals = [status, datetime.now(timezone.utc).isoformat()]
            if proxy_ip:
                sets.append("proxy_ip_used = ?")
                vals.append(proxy_ip)
            if tiktok_post_id:
                sets.append("tiktok_post_id = ?")
                vals.append(tiktok_post_id)
            if notes:
                sets.append("notes = ?")
                vals.append(notes)
            vals.append(post_id)
            conn.execute(
                f"UPDATE posts SET {', '.join(sets)} WHERE id = ?", vals
            )

    def get_posts_today(self) -> list:
        """Get all posts created today (UTC)."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM posts WHERE date(posted_at) = ?", (today,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_posted_count_today(self) -> int:
        """Count successfully posted videos today."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM posts WHERE date(posted_at) = ? AND status = 'POSTED'",
                (today,)
            ).fetchone()
            return row["cnt"]

    def get_last_post_time(self, product_name: str = None) -> Optional[datetime]:
        """Get the most recent post time, optionally filtered by product."""
        with self._connect() as conn:
            if product_name:
                row = conn.execute(
                    "SELECT posted_at FROM posts WHERE product_name = ? AND status = 'POSTED' ORDER BY posted_at DESC LIMIT 1",
                    (product_name,)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT posted_at FROM posts WHERE status = 'POSTED' ORDER BY posted_at DESC LIMIT 1"
                ).fetchone()
        if row and row["posted_at"]:
            return datetime.fromisoformat(row["posted_at"])
        return None

    # =========================================================================
    # RAW STOCK
    # =========================================================================

    def sync_raw_stock(self, product_name: str, filenames: list):
        """Upsert raw stock entries for a product. Adds new files, keeps existing."""
        with self._connect() as conn:
            for fname in filenames:
                conn.execute(
                    """INSERT OR IGNORE INTO raw_stock (product_name, filename)
                       VALUES (?, ?)""",
                    (product_name, fname)
                )

    def get_raw_stock_counts(self) -> dict:
        """Get AVAILABLE raw video counts per product: {product_name: count}.
        Excludes raws already consumed (posted_at set) so stock reflects what
        can still be posted."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT product_name, COUNT(*) as cnt
                   FROM raw_stock
                   WHERE posted_at IS NULL
                   GROUP BY product_name"""
            ).fetchall()
            return {r["product_name"]: r["cnt"] for r in rows}

    def get_unused_raw_videos(self, product_name: str, exclude_recent: int = 5) -> list:
        """Get raw videos for a product that haven't been used recently.
        Excludes the N most recently used to avoid repetition."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM raw_stock
                   WHERE product_name = ? AND posted_at IS NULL
                   ORDER BY last_used ASC NULLS FIRST, use_count ASC
                   LIMIT 100""",
                (product_name,)
            ).fetchall()
            results = [dict(r) for r in rows]
            # Return all but the most recently used N
            if len(results) > exclude_recent:
                return results
            return results

    def mark_raw_video_used(self, raw_stock_id: int):
        """Mark a raw video as used (increment count, set last_used)."""
        with self._connect() as conn:
            conn.execute(
                """UPDATE raw_stock
                   SET use_count = use_count + 1, last_used = ?
                   WHERE id = ?""",
                (datetime.now(timezone.utc).isoformat(), raw_stock_id)
            )

    # =========================================================================
    # CAPTION POOL
    # =========================================================================

    def add_caption(self, product_name: str, caption_text: str,
                    description_text: str = None, product_tag_text: str = None,
                    source: str = "manual", compliance_checked: bool = False,
                    original_text: str = None) -> int:
        """Add a caption to the pool. Returns caption ID."""
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO caption_pool
                   (product_name, caption_text, description_text, product_tag_text, compliance_checked, source, original_text)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (product_name, caption_text, description_text, product_tag_text, int(compliance_checked), source, original_text)
            )
            return cur.lastrowid

    def get_available_captions(self, product_name: str, limit: int = 10) -> list:
        """Get compliance-checked captions for a product (or generic ones).
        Prioritizes least-used captions."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM caption_pool
                   WHERE (product_name = ? OR product_name IS NULL)
                   AND compliance_checked = 1
                   ORDER BY times_used ASC, last_used ASC NULLS FIRST
                   LIMIT ?""",
                (product_name, limit)
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_caption_used(self, caption_id: int):
        """Increment usage count for a caption."""
        with self._connect() as conn:
            conn.execute(
                """UPDATE caption_pool
                   SET times_used = times_used + 1, last_used = ?
                   WHERE id = ?""",
                (datetime.now(timezone.utc).isoformat(), caption_id)
            )

    def get_caption_pool_for_product(self, product_name: str) -> list:
        """Get all captions for a product (for /captions command)."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM caption_pool
                   WHERE product_name = ? OR product_name IS NULL
                   ORDER BY times_used DESC""",
                (product_name,)
            ).fetchall()
            return [dict(r) for r in rows]

    # =========================================================================
    # COMPETITOR DATA
    # =========================================================================

    def save_competitor_data(self, entries: list):
        """Bulk insert competitor scrape results."""
        with self._connect() as conn:
            for entry in entries:
                conn.execute(
                    """INSERT INTO competitor_data
                       (competitor_handle, post_url, product_keywords, hashtags,
                        sound_used, view_count, caption_text)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (entry.get("competitor_handle"),
                     entry.get("post_url"),
                     entry.get("product_keywords"),
                     json.dumps(entry.get("hashtags", [])),
                     entry.get("sound_used"),
                     entry.get("view_count", 0),
                     entry.get("caption_text"))
                )

    def get_top_competitor_posts(self, min_views: int = 10000, limit: int = 20) -> list:
        """Get viral competitor posts for AI strategy reference."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM competitor_data
                   WHERE view_count >= ?
                   ORDER BY view_count DESC
                   LIMIT ?""",
                (min_views, limit)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_recent_competitor_data(self, days: int = 7) -> list:
        """Get competitor data from the last N days."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM competitor_data
                   WHERE scraped_at >= datetime('now', ?)
                   ORDER BY scraped_at DESC""",
                (f"-{days} days",)
            ).fetchall()
            return [dict(r) for r in rows]

    # =========================================================================
    # SYSTEM EVENTS
    # =========================================================================

    def log_event(self, event_type: str, message: str, metadata: dict = None):
        """Log a system event."""
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO system_events (event_type, message, metadata)
                   VALUES (?, ?, ?)""",
                (event_type, message, json.dumps(metadata) if metadata else None)
            )

    def get_recent_events(self, limit: int = 20) -> list:
        """Get recent system events (for /logs command)."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM system_events
                   ORDER BY occurred_at DESC
                   LIMIT ?""",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    # =========================================================================
    # AGGREGATE QUERIES
    # =========================================================================

    def get_performance_summary(self, days: int = 7) -> dict:
        """Get posting performance summary for AI strategy."""
        with self._connect() as conn:
            # Posts per product in last N days
            by_product = conn.execute(
                """SELECT product_name,
                   COUNT(*) as post_count,
                   AVG(views) as avg_views,
                   AVG(likes) as avg_likes,
                   SUM(views) as total_views
                   FROM posts
                   WHERE posted_at >= datetime('now', ?)
                   AND status = 'POSTED'
                   GROUP BY product_name""",
                (f"-{days} days",)
            ).fetchall()

            # Total posts today
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            today_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM posts WHERE date(posted_at) = ? AND status = 'POSTED'",
                (today,)
            ).fetchone()

            return {
                "by_product": [dict(r) for r in by_product],
                "today_count": today_count["cnt"],
                "period_days": days
            }

    def get_products_due_next(self) -> list:
        """Get products sorted by: least recently posted, most stock."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT rs.product_name,
                   COUNT(CASE WHEN rs.posted_at IS NULL THEN 1 END) as stock_count,
                   MAX(p.posted_at) as last_posted,
                   COALESCE(MAX(p.posted_at), '1970-01-01') as sort_key
                   FROM raw_stock rs
                   LEFT JOIN posts p ON p.product_name = rs.product_name AND p.status = 'POSTED'
                   GROUP BY rs.product_name
                   HAVING stock_count > 0
                   ORDER BY sort_key ASC, stock_count DESC"""
            ).fetchall()
            return [dict(r) for r in rows]