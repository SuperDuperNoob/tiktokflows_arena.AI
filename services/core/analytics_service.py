"""Analytics service for metrics, reconciliation, and reporting."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.utils.db_utils import get_conn, ensure_schema
from services.utils.timezone import (
    OWN_HANDLE,
    human,
    utcnow,
    stamp,
)
from services.utils.quality import clamp_telegram
from services.utils.paths import daily_report as daily_report_path
from services.utils.stock import scan_stock
from services.utils.queue import queue_count
from services.utils.burn_log import recent_burns, quality_check as burn_quality_check
from services.infrastructure.config import get_config
from services.infrastructure.database import Database
from services.infrastructure.logging import get_logger
from services.infrastructure.competitor_scraper import CompetitorScraper

logger = get_logger(__name__)

# Constants
MATCH_WINDOW_H = 36
LOW_STOCK = 5


def _parse_dt(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _norm(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"[^\w\s]", " ", str(text).lower(), flags=re.UNICODE)
    return re.sub(r"\s+", " ", cleaned).strip()


def _short(text: str, n: int = 32) -> str:
    text = " ".join((text or "").split())
    return (text[: n - 1] + "…") if len(text) > n else (text or "-")


class AnalyticsService:
    """Service for analytics, reconciliation, and reporting."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get dashboard analytics data."""
        return {
            "views_today": 0,
            "views_this_week": 0,
            "posts_today": 0,
            "top_products": [],
            "recent_posts": [],
        }

    def generate_ops_report(self, days: int = 3, full: bool = False) -> str:
        """Generate OPS report."""
        return self._build_report(days, full)

    def _build_report(self, days: int = 3, full: bool = False) -> str:
        blocks: list[list[str]] = []
        blocks.append(self._quality_lines(full))
        blocks.append(self._left_lines())
        if not Path(self.db_path).exists():
            blocks.append(["📤 Posted: no DB yet"])
        else:
            try:
                conn = get_conn()
                ensure_schema(conn)
                blocks.append(self._posted_lines(conn, days, full))
                blocks.append(self._performance_lines(conn, days, full))
                conn.close()
            except Exception as e:
                blocks.append([f"⚠️ report error: {e}"])
        body = "\n".join("\n".join(b) for b in blocks if b)
        return clamp_telegram(f"{body}\n\n📅 {stamp()}")

    def _quality_lines(self, full: bool) -> list[str]:
        q = burn_quality_check(10)
        if not q:
            return []
        if q.get("is_still"):
            out = [f"🚨 LAST BURN WAS A STILL IMAGE: {q['frames']} frame(s) "
                   f"({q.get('duration_s', 0)}s)"]
            if q["still_count"] > 1:
                out.append(f"   {q['still_count']}/{q['count']} recent burns affected")
            out.append("   Uploads will show as a static photo on TikTok.")
            out.append("   Run: python3 check_burns.py --quarantine")
            return out
        if q["degraded"]:
            out = [f"⚠️ VIDEO QUALITY LOW: {q['latest_mb_per_sec']:.2f} MB/s "
                   f"(~{q['latest_kbps']} kbps), floor {q.get('min_mb_per_sec', 0.30)}"]
            if q["low_count"] > 1:
                out.append(f"   {q['low_count']}/{q['count']} recent burns affected")
            out.append(f"   crf={q['crf']} maxrate={q['maxrate']} — TikTok re-encodes, "
                       f"so this looks worse after upload")
            return out
        if full:
            frames = (f", {q['frames']} frames" if q.get("frames") is not None else "")
            return [f"🎬 Quality OK: {q['latest_mb_per_sec']:.2f} MB/s "
                    f"(~{q['latest_kbps']} kbps, crf={q['crf']}{frames}), "
                    f"{q['count']} burns avg {q['avg_mb_per_sec']:.2f}"]
        return []

    def _left_lines(self) -> list[str]:
        stock = scan_stock()
        total_raw = sum(stock.values())
        out = [f"📹 Stock: {len(stock)} products | {total_raw} raw videos"]
        for name, cnt in sorted(stock.items(), key=lambda x: (x[1], x[0].casefold())):
            icon = "🔴" if cnt < LOW_STOCK else "🟡" if cnt < 10 else "🟢"
            out.append(f"{icon} {name}: {cnt}")
        queued = queue_count()
        if queued:
            out.append(f"📦 {queued} rendered, waiting to upload")
        return out

    def _posted_lines(self, conn, days: int, full: bool) -> list[str]:
        per_day = self._posts_per_day(conn, days)
        total = sum(n for _, n in per_day)
        if not total:
            return [f"📤 Posted {days}d: nothing"]
        breakdown = " · ".join(f"{d[5:]} {n}" for d, n in per_day)
        return [f"📤 Posted {days}d: {total} ({breakdown})"]

    def _posts_per_day(self, conn, days: int) -> list[tuple[str, int]]:
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

    def _recent_posts(self, conn, days: int) -> list[dict]:
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

    def _views_delta(self, conn, days: int) -> int:
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

    def _performance_lines(self, conn, days: int, full: bool) -> list[str]:
        posts = self._recent_posts(conn, days)
        if not posts:
            return []
        measured = [p for p in posts if p["last_snap"]]
        out: list[str] = []
        d1 = self._views_delta(conn, 1)
        out.append(f"📈 24h +{human(d1)} views (all videos)")
        if not measured:
            out.append("⏳ No metrics yet for these posts (scrape pending)")
            return out
        best = measured[0]
        out.append(f"🥇 {best['product_folder']} {human(best['views'])} views · "
                   f"{human(best['interactions'])} int · {best['posted_day'][5:]}")
        if full and best["caption"]:
            out.append(f"    “{_short(best['caption'], 48)}”")
        if len(measured) > 1:
            worst = measured[-1]
            out.append(f"🥉 {worst['product_folder']} {human(worst['views'])} views · "
                       f"{worst['posted_day'][5:]}")
        top_int = max(measured, key=lambda p: p["interactions"])
        if top_int["video_id"] != best["video_id"] and top_int["interactions"]:
            out.append(f"💬 Most engaging: {top_int['product_folder']} "
                       f"{human(top_int['interactions'])} int on "
                       f"{human(top_int['views'])} views")
        if full:
            out.append(f"— all {len(posts)} posts, {days}d —")
            for p in posts:
                when = p["posted_day"][5:]
                if p["last_snap"]:
                    out.append(f"  {when} {p['product_folder']}: {human(p['views'])} v · "
                               f"{human(p['likes'])} l · {human(p['shares'])} s · "
                               f"{human(p['comments'])} c")
                else:
                    out.append(f"  {when} {p['product_folder']}: (no metrics yet)")
        return out

    def generate_growth_report(self) -> Dict[str, Any]:
        """Generate growth strategy report via AIAdapter."""
        from services.infrastructure.ai_adapter import AIAdapter
        adapter = AIAdapter()
        return adapter.generate_growth_report(days=7, dry_run=True)

    def reconcile_metrics(self, window_days: int = 14) -> Dict[str, Any]:
        """Reconcile local uploads with scraped metrics."""
        conn = get_conn()
        ensure_schema(conn)
        stats = self._reconcile(conn, window_days)
        conn.close()
        return stats

    def _reconcile(self, conn, window_days: int = 14, verbose: bool = True) -> dict:
        since = (date.today() - timedelta(days=window_days)).isoformat()

        unmatched = conn.execute(
            """SELECT video_id, product_folder, caption, posted_at, tiktok_video_id
               FROM videos
               WHERE (tiktok_video_id IS NULL OR tiktok_video_id = '')
                 AND posted_at >= ?
               ORDER BY posted_at DESC""", (since,)).fetchall()

        scraped = conn.execute(
            """SELECT video_id, caption, posted_at, MAX(snap_date) AS last_snap
               FROM competitor_videos
               WHERE handle = ? AND snap_date >= ?
               GROUP BY video_id""", (OWN_HANDLE, since)).fetchall()

        taken = {r["tiktok_video_id"]
                 for r in conn.execute("SELECT tiktok_video_id FROM videos "
                                       "WHERE tiktok_video_id IS NOT NULL "
                                       "AND tiktok_video_id != ''")}
        pool = [s for s in scraped if s["video_id"] not in taken]

        matched = 0
        for row in unmatched:
            posted = _parse_dt(row["posted_at"])
            want = _norm(row["caption"])
            hit = None
            if want:
                for cand in pool:
                    if _norm(cand["caption"]) != want:
                        continue
                    cpost = _parse_dt(cand["posted_at"])
                    if posted and cpost and abs((cpost - posted).total_seconds()) > MATCH_WINDOW_H * 3600:
                        continue
                    hit = cand
                    break
            if hit is None and posted:
                near = []
                for cand in pool:
                    cpost = _parse_dt(cand["posted_at"])
                    if not cpost:
                        continue
                    delta = abs((cpost - posted).total_seconds())
                    if delta <= MATCH_WINDOW_H * 3600:
                        near.append((delta, cand))
                if len(near) == 1:
                    hit = near[0][1]
                elif len(near) > 1:
                    near.sort(key=lambda x: x[0])
                    if near[1][0] - near[0][0] > 3600:
                        hit = near[0][1]
            if hit is None:
                continue
            conn.execute("UPDATE videos SET tiktok_video_id = ?, matched_at = ? "
                         "WHERE video_id = ?",
                         (hit["video_id"], utcnow(), row["video_id"]))
            pool = [p for p in pool if p["video_id"] != hit["video_id"]]
            matched += 1
            if verbose:
                logger.info(f"[reconcile] {row['video_id']} -> {hit['video_id']} "
                           f"({row['product_folder']})")

        conn.commit()

        copied = conn.execute("""
            INSERT INTO daily_metrics
                   (video_id, snap_date, views, likes, shares, saves, comments, captured_at)
            SELECT v.video_id, cv.snap_date, cv.views, cv.likes, cv.shares, 0,
                   cv.comments, cv.captured_at
            FROM videos v
            JOIN competitor_videos cv ON cv.video_id = v.tiktok_video_id AND cv.handle = ?
            WHERE v.tiktok_video_id IS NOT NULL AND v.tiktok_video_id != ''
              AND cv.snap_date >= ?
            ON CONFLICT(video_id, snap_date) DO UPDATE SET
                views=excluded.views, likes=excluded.likes,
                shares=excluded.shares, comments=excluded.comments,
                captured_at=excluded.captured_at""",
            (OWN_HANDLE, since)).rowcount
        conn.commit()

        linked = conn.execute("SELECT COUNT(*) c FROM videos WHERE tiktok_video_id "
                              "IS NOT NULL AND tiktok_video_id != ''").fetchone()["c"]
        pending = conn.execute(
            """SELECT COUNT(*) c FROM videos
               WHERE (tiktok_video_id IS NULL OR tiktok_video_id = '') AND posted_at >= ?""",
            (since,)).fetchone()["c"]
        metric_rows = conn.execute("SELECT COUNT(*) c FROM daily_metrics "
                                   "WHERE snap_date >= ?", (since,)).fetchone()["c"]
        return {
            "new_matches": matched,
            "metric_rows_written": max(copied, 0),
            "linked_total": linked,
            "still_unmatched": pending,
            "daily_metrics_rows": metric_rows,
            "scraped_available": len(scraped),
        }

    def get_performance_summary(self, days: int = 7) -> Dict[str, Any]:
        """Get performance summary."""
        conn = get_conn()
        ensure_schema(conn)
        try:
            # Posts per product in last N days
            by_product = conn.execute("""
                SELECT product_name,
                       COUNT(*) as post_count,
                       AVG(views) as avg_views,
                       AVG(likes) as avg_likes,
                       SUM(views) as total_views
                FROM posts
                WHERE posted_at >= datetime('now', ?)
                AND status = 'POSTED'
                GROUP BY product_name""",
                (f"-{days} days",)).fetchall()

            today = date.today().isoformat()
            today_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM posts WHERE date(posted_at) = ? AND status = 'POSTED'",
                (today,)).fetchone()

            return {
                "by_product": [dict(r) for r in by_product],
                "today_count": today_count["cnt"] if today_count else 0,
                "period_days": days
            }
        finally:
            conn.close()

    def run_daily_jobs(self, db: Database, config: dict) -> None:
        """Run daily analytics jobs: scrape, reconcile, growth, report."""
        # Scrape competitor data
        try:
            scraper = CompetitorScraper(config.get("apify", {}), db)
            summary = scraper.scrape_all()
            logger.info("Scrape complete: %s", summary)
        except Exception as e:
            logger.error("Daily scrape failed: %s", e)

        # Reconcile metrics
        try:
            conn = get_conn()
            ensure_schema(conn)
            stats = self._reconcile(conn, verbose=False)
            logger.info("Reconcile: %s", stats)
            conn.close()
        except Exception as e:
            logger.error("Reconcile failed: %s", e)

        # Generate report
        try:
            report = self._build_report(days=3)
            logger.info("Report generated: %s", report[:100] if report else "empty")
        except Exception as e:
            logger.error("Report failed: %s", e)