"""Competitor Scraper via Apify — TikTok Scraper (clockworks/tiktok-scraper)

Chosen actor: `clockworks/tiktok-scraper`. This is the same actor the
battle-tested tiktokflow_vps pipeline ran in production, and its output fields
map 1:1 to the analytics schema (`competitor_videos` / `competitor_daily`) that
reconcile_metrics.py, ai_growth.py and generate_report.py read.

Why not the old `clockworks/tiktok-profile-scraper`? That actor returns
profile-LEVEL fields only (bio, follower counts, hearts) with no per-post
videos, so it could never feed the per-video analytics tables.

Writes:
  - `competitor_videos` + `competitor_daily`  (analytics schema via lib) — the
    source of truth for /growth, reconcile and the OPS report
  - `competitor_data` (legacy db.py table)     — still used by the web dashboard

Runs once daily to preserve Apify budget.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import date, datetime, timezone
from typing import List, Optional

import httpx

from services.infrastructure.config import get_config
from services.infrastructure.database import Database
from services.utils.paths import db_path
from services.utils.db_utils import get_conn, ensure_schema

logger = logging.getLogger(__name__)

APIFY_BASE = "https://api.apify.com/v2"
# The battle-tested actor (matches tiktokflow_vps production).
DEFAULT_ACTOR = "clockworks/tiktok-scraper"


class CompetitorScraper:
    """Scrapes competitor TikTok profiles via Apify and stores analytics."""

    def __init__(self, config: dict, db: Database):
        self.api_token = config.get("api_token") or config.get("token", "")
        self.actor_id = config.get("actor_id", DEFAULT_ACTOR)
        competitors = config.get("competitors", [])
        # Default to own + rival handle so own metrics are always collected.
        cfg = get_config()
        self.competitors = competitors or [cfg.get("tiktok", "session_username", default="kumpul.shop"),
                                           cfg.get("analytics", "rival_handle", default="reski.reski700")]
        self.results_per_page = config.get("results_per_page", 20)
        self.max_competitors = config.get("max_competitors", 5)
        self.db = db

        if not self.api_token or self.api_token in ("your-apify-token-here", ""):
            logger.warning("Apify API token not configured — scraper will be no-op")

    # -------------------------------------------------------------- entry ----

    def scrape_all(self) -> dict:
        if not self.api_token or self.api_token == "your-apify-token-here":
            return {"error": "Apify token not configured"}

        summary = {}
        handles = self.competitors[:self.max_competitors]
        # Batch all profiles in one actor run (cheaper, one poll loop).
        items = self._run_apify(handles)
        if not items:
            logger.warning("Apify returned no items for %s", handles)
            return {h: {"posts_scraped": 0, "viral_posts": 0} for h in handles}

        by_handle = self._group_by_handle(items)
        for handle, videos in by_handle.items():
            try:
                self._store(handle, videos)
                viral = sum(1 for v in videos if v.get("playCount", 0) >= 10000)
                summary[handle] = {"posts_scraped": len(videos), "viral_posts": viral}
                logger.info("  → @%s: %d posts, %d viral", handle, len(videos), viral)
            except Exception as e:
                logger.error("Failed to store @%s: %s", handle, e)
                summary[handle] = {"error": str(e)}

        self.db.log_event(
            "SCRAPE_COMPLETE",
            f"Competitor scrape completed: {len(summary)} handles processed",
            metadata={"summary": summary})
        return summary

    # ------------------------------------------------------------- apify ----

    def _run_apify(self, profiles: List[str]) -> List[dict]:
        """Start one actor run for all profiles, poll, fetch dataset items."""
        run_input = {
            "profiles": profiles,
            "resultsPerPage": self.results_per_page,
            "profileScrapeSections": ["videos"],
            "profileSorting": "latest",
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
            "shouldDownloadMusicCovers": False,
            "shouldDownloadSubtitles": False,
            "excludePinnedPosts": False,
        }
        run_id = self._start_actor_run(run_input)
        if not run_id:
            return []
        dataset_id = self._wait_for_run(run_id, timeout=420)
        if not dataset_id:
            return []
        return self._fetch_dataset_items(dataset_id)

    def _start_actor_run(self, run_input: dict) -> Optional[str]:
        url = f"{APIFY_BASE}/acts/{self.actor_id}/runs"
        headers = {"Authorization": f"Bearer {self.api_token}"}
        try:
            resp = httpx.post(url, json=run_input, headers=headers, timeout=30)
            resp.raise_for_status()
            run_id = resp.json()["data"]["id"]
            logger.info("Started Apify actor run: %s", run_id)
            return run_id
        except httpx.HTTPStatusError as e:
            logger.error("Apify API error (%s): %s", e.response.status_code, e.response.text)
            return None
        except Exception as e:
            logger.error("Failed to start Apify actor: %s", e)
            return None

    def _wait_for_run(self, run_id: str, timeout: int = 420) -> Optional[str]:
        url = f"{APIFY_BASE}/actor-runs/{run_id}"
        headers = {"Authorization": f"Bearer {self.api_token}"}
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = httpx.get(url, headers=headers, timeout=15)
                resp.raise_for_status()
                data = resp.json()["data"]
                status = data["status"]
                if status == "SUCCEEDED":
                    return data["defaultDatasetId"]
                if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                    logger.error("Actor run %s ended with status: %s", run_id, status)
                    return None
                time.sleep(10)
            except Exception as e:
                logger.warning("Poll error for run %s: %s", run_id, e)
                time.sleep(10)
        return None

    def _fetch_dataset_items(self, dataset_id: str) -> List[dict]:
        url = f"{APIFY_BASE}/datasets/{dataset_id}/items"
        headers = {"Authorization": f"Bearer {self.api_token}"}
        try:
            resp = httpx.get(url, headers=headers,
                             params={"format": "json", "clean": True}, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error("Failed to fetch dataset %s: %s", dataset_id, e)
            return []

    # ------------------------------------------------------------ parsing ----

    def _group_by_handle(self, items: List[dict]) -> dict:
        by_handle = {}
        for item in items:
            handle = (item.get("authorMeta") or {}).get("name", "unknown").lower()
            by_handle.setdefault(handle, []).append(item)
        return by_handle

    def _store(self, handle: str, videos: List[dict]) -> None:
        """Write to analytics tables (competitor_daily + competitor_videos)."""
        conn = get_conn()
        ensure_schema(conn)
        snap = date.today().isoformat()
        captured = datetime.now(timezone.utc).isoformat()

        top = max(videos, key=lambda v: v.get("playCount", 0) or 0, default={})
        music = top.get("musicMeta") or {}
        hashtag_freq = {}
        for v in videos:
            for ht in (v.get("hashtags") or []):
                tag = (ht.get("name") if isinstance(ht, dict) else str(ht)) or ""
                if tag:
                    hashtag_freq[tag] = hashtag_freq.get(tag, 0) + 1
        top_hashtag = max(hashtag_freq, key=hashtag_freq.get, default="")

        conn.execute("""\n            INSERT INTO competitor_daily\n                (handle, snap_date, followers, posts_today, top_sound_id,\n                 top_sound_name, top_hashtag, top_views, captured_at)\n            VALUES (?,?,?,?,?,?,?,?,?)\n            ON CONFLICT(handle, snap_date) DO UPDATE SET\n                followers=excluded.followers, posts_today=excluded.posts_today,\n                top_sound_id=excluded.top_sound_id,\n                top_sound_name=excluded.top_sound_name,\n                top_hashtag=excluded.top_hashtag, top_views=excluded.top_views,\n                captured_at=excluded.captured_at\n        """, (handle, snap,
              (top.get("authorMeta") or {}).get("fans", 0),
              len(videos),
              str(music.get("musicId", "")),
              music.get("musicName", ""),
              top_hashtag,
              top.get("playCount", 0),
              captured))

        rows = []
        for v in videos:
            vid_id = str(v.get("id", ""))
            if not vid_id:
                continue
            tags = [h.get("name", "") if isinstance(h, dict) else str(h)
                    for h in (v.get("hashtags") or [])]
            m = v.get("musicMeta") or {}
            posted = (""
                      if not v.get("createTime")
                      else datetime.fromtimestamp(v["createTime"], tz=timezone.utc).isoformat())
            rows.append((
                vid_id, handle, v.get("text", "") or "",
                json.dumps(tags, ensure_ascii=False),
                str(m.get("musicId", "")), m.get("musicName", ""),
                m.get("musicAuthor", ""),
                v.get("playCount", 0), v.get("diggCount", 0),
                v.get("shareCount", 0), v.get("commentCount", 0),
                posted, snap, captured))
        if rows:
            conn.executemany("""\n                INSERT INTO competitor_videos\n                    (video_id, handle, caption, hashtags_json, sound_id,\n                     sound_name, sound_author, views, likes, shares, comments,\n                     posted_at, snap_date, captured_at)\n                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)\n                ON CONFLICT(video_id, snap_date) DO UPDATE SET\n                    views=excluded.views, likes=excluded.likes,\n                    shares=excluded.shares, comments=excluded.comments,\n                    captured_at=excluded.captured_at\n            """, rows)
        conn.commit()

        # Also feed the legacy dashboard table (competitor_data) for backwards
        # compatibility with the web UI / get_top_competitor_posts().
        try:
            entries = []
            for v in videos:
                text = v.get("text", "") or ""
                entries.append({
                    "competitor_handle": handle,
                    "post_url": v.get("webVideoUrl", "") or "",
                    "product_keywords": text[:200],
                    "hashtags": json.dumps(
                        [h.get("name", "") if isinstance(h, dict) else str(h)
                         for h in (v.get("hashtags") or [])], ensure_ascii=False),
                    "sound_used": (v.get("musicMeta") or {}).get("musicName", ""),
                    "view_count": v.get("playCount", 0),
                    "caption_text": text[:500],
                })
            if entries:
                self.db.save_competitor_data(entries)
        except Exception as e:
            logger.warning("Legacy dashboard write failed (non-fatal): %s", e)

        conn.close()


def run_daily_scrape(config: dict, db: Database) -> dict:
    """Module-level convenience function used by the orchestrator."""
    scraper = CompetitorScraper(config, db)
    return scraper.scrape_all()


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser(description="Competitor Scraper via Apify")
    ap.add_argument("--dry-run", action="store_true",
                    help="skip actual scraping")
    args = ap.parse_args()

    if args.dry_run:
        print("[dry-run] would scrape competitors")
        sys.exit(0)

    # Note: requires config and db to be set up properly
    print("Competitor scraper - use orchestrator daily job or call service directly")