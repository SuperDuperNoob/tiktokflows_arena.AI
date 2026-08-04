"""
Competitor Monitoring via Apify

Scrapes competitor TikTok profiles using the Apify TikTok Profile Scraper actor.
Runs once daily (configurable) to preserve Apify budget ($5/month).

Extracts: view counts, hashtags, sounds, caption keywords from last N posts.
"""
import json
import logging
import time
from datetime import datetime, timezone
from typing import List, Optional

import httpx

from db import Database

logger = logging.getLogger(__name__)

# Apify API base URL
APIFY_BASE = "https://api.apify.com/v2"


class CompetitorScraper:
    """Scrapes competitor TikTok profiles via Apify."""

    def __init__(self, config: dict, db: Database):
        self.api_token = config.get("api_token", "")
        self.actor_id = config.get("actor_id", "clockworks/tiktok-profile-scraper")
        self.competitors = config.get("competitors", [])
        self.max_posts = config.get("max_posts_per_competitor", 10)
        self.max_competitors = config.get("max_competitors", 5)
        self.db = db

        if not self.api_token or self.api_token == "your-apify-token-here":
            logger.warning("Apify API token not configured — scraper will be no-op")

    def scrape_all(self) -> dict:
        """
        Scrape all configured competitors.

        Returns:
            Summary dict: {handle: {"posts_scraped": int, "viral_posts": int}}
        """
        if not self.api_token or self.api_token == "your-apify-token-here":
            return {"error": "Apify token not configured"}

        summary = {}
        # Limit to max_competitors to save budget
        handles = self.competitors[:self.max_competitors]

        for handle in handles:
            try:
                logger.info(f"Scraping competitor: {handle}")
                posts = self.scrape_competitor(handle)

                if posts:
                    # Save to database
                    entries = []
                    viral_count = 0
                    for post in posts:
                        entry = self._parse_post(handle, post)
                        if entry:
                            entries.append(entry)
                            if entry.get("view_count", 0) >= 10000:
                                viral_count += 1

                    self.db.save_competitor_data(entries)

                    summary[handle] = {
                        "posts_scraped": len(entries),
                        "viral_posts": viral_count
                    }

                    logger.info(f"  → {len(entries)} posts scraped, {viral_count} viral")
                else:
                    summary[handle] = {"posts_scraped": 0, "viral_posts": 0}

            except Exception as e:
                logger.error(f"Failed to scrape {handle}: {e}")
                summary[handle] = {"error": str(e)}

        # Log the event
        self.db.log_event(
            "SCRAPE_COMPLETE",
            f"Competitor scrape completed: {len(summary)} handles processed",
            metadata={"summary": summary}
        )

        return summary

    def scrape_competitor(self, handle: str) -> List[dict]:
        """
        Scrape a single competitor's TikTok profile.

        Uses the Apify actor to fetch the profile, then returns raw post data.
        """
        # Build the run input
        run_input = {
            "profiles": [handle],
            "maxItems": self.max_posts,
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
        }

        # Start the actor run
        run_id = self._start_actor_run(run_input)
        if not run_id:
            return []

        # Wait for completion (with timeout)
        dataset_id = self._wait_for_run(run_id, timeout=300)
        if not dataset_id:
            logger.error(f"Actor run did not complete within timeout for {handle}")
            return []

        # Fetch results from the dataset
        items = self._fetch_dataset_items(dataset_id)
        return items

    def _start_actor_run(self, run_input: dict) -> Optional[str]:
        """Start an Apify actor run and return the run ID."""
        url = f"{APIFY_BASE}/acts/{self.actor_id}/runs"
        headers = {"Authorization": f"Bearer {self.api_token}"}

        try:
            resp = httpx.post(
                url,
                json=run_input,
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            run_id = data["data"]["id"]
            logger.info(f"Started Apify actor run: {run_id}")
            return run_id
        except httpx.HTTPStatusError as e:
            logger.error(f"Apify API error ({e.response.status_code}): {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Failed to start Apify actor: {e}")
            return None

    def _wait_for_run(self, run_id: str, timeout: int = 300) -> Optional[str]:
        """Poll until the actor run completes. Returns dataset ID or None."""
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
                elif status in ("FAILED", "ABORTED", "TIMED-OUT"):
                    logger.error(f"Actor run {run_id} ended with status: {status}")
                    return None

                # Still running — wait and poll again
                time.sleep(10)

            except Exception as e:
                logger.warning(f"Poll error for run {run_id}: {e}")
                time.sleep(10)

        return None

    def _fetch_dataset_items(self, dataset_id: str) -> List[dict]:
        """Fetch all items from an Apify dataset."""
        url = f"{APIFY_BASE}/datasets/{dataset_id}/items"
        headers = {"Authorization": f"Bearer {self.api_token}"}

        try:
            resp = httpx.get(
                url,
                headers=headers,
                params={"format": "json", "clean": True},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Failed to fetch dataset {dataset_id}: {e}")
            return []

    def _parse_post(self, handle: str, post: dict) -> Optional[dict]:
        """Parse a raw Apify post into our competitor_data format."""
        try:
            # Apify TikTok scraper returns different field names depending on version.
            # Handle common variations.
            view_count = (
                post.get("playCount")
                or post.get("view_count")
                or post.get("diggCount", 0)  # fallback
            )

            # Extract hashtags from text
            text = post.get("text", "") or post.get("caption", "")
            hashtags = self._extract_hashtags(text)

            # Extract sound/music
            music = post.get("music", {})
            sound_used = ""
            if isinstance(music, dict):
                sound_used = music.get("title", "") or music.get("authorName", "")
            elif isinstance(music, str):
                sound_used = music

            return {
                "competitor_handle": handle,
                "post_url": post.get("webVideoUrl", "") or post.get("post_url", ""),
                "product_keywords": text[:200] if text else "",
                "hashtags": hashtags,
                "sound_used": sound_used,
                "view_count": int(view_count) if view_count else 0,
                "caption_text": text[:500] if text else "",
            }
        except Exception as e:
            logger.warning(f"Failed to parse post from {handle}: {e}")
            return None

    def _extract_hashtags(self, text: str) -> List[str]:
        """Extract hashtags from text."""
        import re
        return re.findall(r'#(\w+)', text or "")


def run_daily_scrape(config: dict, db: Database) -> dict:
    """Module-level convenience function."""
    scraper = CompetitorScraper(config, db)
    return scraper.scrape_all()
