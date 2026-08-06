"""Analytics repository for managing analytics data."""

from typing import Any, Dict, List, Optional
from datetime import date, datetime, timedelta

from .base import BaseRepository
from services.infrastructure.config import get_config


class AnalyticsRepository(BaseRepository):
    """Repository for analytics operations."""

    def __init__(self, db_path: str):
        super().__init__(db_path)

    def get_table_name(self) -> str:
        return "videos"  # Virtual table name

    def log_video(self, video_data: Dict[str, Any]) -> int:
        """Log a video to analytics."""
        data = {
            "video_id": video_data.get("video_id", ""),
            "product_folder": video_data.get("product_folder", ""),
            "caption": video_data.get("caption", ""),
            "hashtags_json": video_data.get("hashtags_json", "[]"),
            "sound_id": video_data.get("sound_id", ""),
            "sound_name": video_data.get("sound_name", ""),
            "posted_at": video_data.get("posted_at", datetime.utcnow().isoformat()),
        }
        return self.insert("videos", data)

    def get_recent_posts(self, days: int = 3) -> List[Dict[str, Any]]:
        """Get recent posts with metrics."""
        since = (date.today() - timedelta(days=days)).isoformat()
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
        rows = self.fetchall(query, (since,))
        return rows

    def get_own_performance(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get own performance by product."""
        since = (date.today() - timedelta(days=days)).isoformat()
        query = """
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
                COUNT(*) AS uploads,
                CAST(SUM(l.views) AS INTEGER) AS sum_views,
                CAST(AVG(l.views) AS INTEGER) AS avg_views,
                MAX(l.views) AS best_views,
                CAST(SUM(l.likes) AS INTEGER) AS sum_likes,
                ROUND(100.0 * SUM(l.likes) / NULLIF(SUM(l.views), 0), 2) AS engage_pct
            FROM latest l
            JOIN videos v ON v.video_id = l.video_id
            WHERE l.rn = 1
            GROUP BY product_folder
            ORDER BY avg_views DESC
        """
        rows = self.fetchall(query, (since,))
        return rows

    def get_views_delta(self, days: int = 1) -> int:
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
        row = self.fetchone(query, (today, prior))
        return int(row["delta"] or 0) if row else 0

    def get_rival_gap(self) -> Optional[Dict[str, Any]]:
        """Get gap between own and rival performance."""
        query = """
            SELECT handle, snap_date, followers, posts_today,
                   top_sound_name, top_hashtag, top_views
            FROM competitor_daily
            WHERE handle IN (?, ?)
            ORDER BY snap_date DESC
        """
        # Get handles from config
        from services.infrastructure.config import get_config
        cfg = get_config()
        own_handle = cfg.get("tiktok", "session_username", "kumpul.shop").lower()
        rival_handle = cfg.get("analytics", "rival_handle", "reski.reski700").lower()

        rows = self.fetchall(query, (own_handle, rival_handle))
        if len(rows) < 2:
            return None

        own = rows[0] if rows[0]["handle"] == own_handle else rows[1]
        rival = rows[1] if rows[1]["handle"] == rival_handle else rows[0]

        own_v = own.get("top_views") or 0
        rival_v = rival.get("top_views") or 0

        return {
            "own_handle": own_handle,
            "rival_handle": rival_handle,
            "own_views": own_v,
            "rival_views": rival_v,
            "gap": rival_v - own_v,
            "behind": rival_v > own_v,
            "own_date": own.get("snap_date"),
            "rival_date": rival.get("snap_date"),
            "stale": own.get("snap_date") != date.today().isoformat(),
        }