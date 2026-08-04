#!/usr/bin/env python3
"""
reconcile_metrics.py - close the tracking loop (port of reconcile_own_metrics.py).

The uploader invents a local id when it logs an upload (Biocho_1753612345_4821);
the scraper stores the real TikTok id for the same clip (7398211122334455).
Those ids never match, so videos JOIN daily_metrics returned zero rows forever.

This matches rows in `videos` (our upload log) against `competitor_videos`
where handle = own account (the scrape), then copies the scraped metrics into
`daily_metrics` under our own video_id. Matching, strongest first:

  1. videos.tiktok_video_id already set from a previous run
  2. exact overlay-caption match, scrape within +/- MATCH_WINDOW_H of posting
  3. closest post time within the window, when only one candidate is free

Idempotent and safe to run every cycle. Runs automatically after a scrape.

Usage:  python3 reconcile_metrics.py [--days N] [--quiet]
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime, timedelta, timezone

import lib
from lib import OWN_HANDLE, ensure_schema, get_conn, human, utcnow

MATCH_WINDOW_H = 36


def _parse_dt(value: str):
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


def reconcile(conn, window_days: int = 14, verbose: bool = True) -> dict:
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
            print(f"[reconcile] {row['video_id']} -> {hit['video_id']} "
                  f"({row['product_folder']})")
    conn.commit()

    copied = conn.execute(
        """INSERT INTO daily_metrics
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Link own uploads to scraped metrics")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    conn = get_conn()
    ensure_schema(conn)
    stats = reconcile(conn, window_days=args.days, verbose=not args.quiet)
    conn.close()
    print(f"[reconcile] matched {stats['new_matches']} new | "
          f"linked {stats['linked_total']} total | "
          f"metrics rows {human(stats['daily_metrics_rows'])} | "
          f"unmatched {stats['still_unmatched']}")
    if stats["linked_total"] == 0 and stats["scraped_available"] == 0:
        print(f"[reconcile] NOTE: no scraped videos for @{OWN_HANDLE}. "
              "Ensure the scraper includes your own handle.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
