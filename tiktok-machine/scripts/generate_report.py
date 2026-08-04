#!/usr/bin/env python3
"""
generate_report.py - post-run OPS report (ported from tiktokflow_vps).

Answers exactly three questions:
  1. What is left - every product folder with its raw count (always in full),
     plus the rendered upload queue.
  2. What got posted (last 3 days, per day).
  3. What performed (best / most-engaging of those posts).

Deliberately does NOT include growth advice or AI - that is /growth's job
(ai_growth.py -> growth_report.txt). Writes ONLY daily_report.txt.

Usage:
  python3 generate_report.py           # what Telegram gets
  python3 generate_report.py --full    # also list every post individually
  python3 generate_report.py --days N  # lookback window for the posted section
"""
from __future__ import annotations

import argparse
import sys

import lib
from lib import (clamp_telegram, db_path, ensure_schema, get_conn, human,
                 posts_per_day, quality_check, queue_count, recent_posts,
                 scan_stock, stamp, views_delta)

LOW_STOCK = 5


def _short(text: str, n: int = 32) -> str:
    text = " ".join((text or "").split())
    return (text[: n - 1] + "…") if len(text) > n else (text or "-")


def posted_lines(conn, days: int, full: bool) -> list[str]:
    per_day = posts_per_day(conn, days)
    total = sum(n for _, n in per_day)
    if not total:
        return [f"📤 Posted {days}d: nothing"]
    breakdown = " · ".join(f"{d[5:]} {n}" for d, n in per_day)
    return [f"📤 Posted {days}d: {total} ({breakdown})"]


def left_lines() -> list[str]:
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


def quality_lines(full: bool) -> list[str]:
    q = quality_check(10)
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
               f"(~{q['latest_kbps']} kbps), floor {lib.MIN_MB_PER_SEC}"]
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


def performance_lines(conn, days: int, full: bool) -> list[str]:
    posts = recent_posts(conn, days)
    if not posts:
        return []
    measured = [p for p in posts if p["last_snap"]]
    out: list[str] = []
    d1 = views_delta(conn, 1)
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


def build(days: int = 3, full: bool = False) -> str:
    blocks: list[list[str]] = []
    blocks.append(quality_lines(full))
    blocks.append(left_lines())
    if not db_path().exists():
        blocks.append(["📤 Posted: no DB yet"])
    else:
        try:
            conn = get_conn()
            ensure_schema(conn)
            blocks.append(posted_lines(conn, days, full))
            blocks.append(performance_lines(conn, days, full))
            conn.close()
        except Exception as e:
            blocks.append([f"⚠️ report error: {e}"])
    body = "\n".join("\n".join(b) for b in blocks if b)
    return clamp_telegram(f"{body}\n\n📅 {stamp()}")


def main() -> int:
    ap = argparse.ArgumentParser(description="TikTokFlow ops report")
    ap.add_argument("--full", action="store_true",
                    help="also list every individual post with its metrics")
    ap.add_argument("--days", type=int, default=3,
                    help="lookback window in days (default 3)")
    args = ap.parse_args()
    report = build(max(1, args.days), args.full)
    print(report)
    try:
        lib.daily_report().parent.mkdir(parents=True, exist_ok=True)
        lib.daily_report().write_text(report, encoding="utf-8")
    except OSError as e:
        print(f"[report] Could not write daily_report.txt: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
