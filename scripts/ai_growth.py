"""
ai_growth.py - TikTok Auto-Growth Engine (cached AI, 1 paid call/day).

Port of tiktokflow_vps/scripts/ai_growth_engine.py (v4.4 lessons):

  - AI is /growth-only and OPT-IN via --ai. Without it the engine runs on the
    DB + local fallback pool for free.
  - Hard cap of ONE paid call per calendar day (business timezone MYT). The
    result is cached in daily_summary.ai_called_at and re-printed on later
    taps, so tapping /growth five times costs one call.
  - A FAILED call is NOT cached, so a network blip does not burn the day's
    budget - the next /growth retries.
  - --dry-run never calls AI and writes nothing.
  - Writes ONLY growth_report.txt. daily_report.txt belongs to generate_report.py.

Run:
  python3 ai_growth.py                 # free, local fallback
  python3 ai_growth.py --ai            # allow one paid call/day
  python3 ai_growth.py --ai --dry-run  # analyse only, write nothing
  python3 ai_growth.py --days 7
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import timedelta

from caption_policy import (AI_CAPTION_RULES, MAX_CAPTION_CHARS, dedup_key,
                            is_too_long, scan_caption, shorten, soften,
                            soften_claims)
import lib
from lib import (burn_jsonl, human, local_now, local_today, own_performance,
                 rival_gap, scan_stock, stamp, views_delta)

PRESET_MAX = 150
AI_TIMEOUT = 45
AI_RETRIES = 2


# ------------------------------------------------------------ analytics ----

def analyze(conn, days: int = 7) -> dict:
    since = (local_today() - timedelta(days=days)).isoformat()
    comp_daily = [dict(r) for r in conn.execute(
        """SELECT handle, snap_date, followers, posts_today, top_sound_name,
                  top_hashtag, top_views
           FROM competitor_daily WHERE snap_date >= ?
           ORDER BY snap_date DESC""", (since,))]
    comp_videos = [dict(r) for r in conn.execute(
        """SELECT handle, caption, sound_name, views, likes, hashtags_json,
                  posted_at
           FROM competitor_videos
           WHERE snap_date >= ? AND handle != ?
           ORDER BY views DESC LIMIT 15""", (since, lib.OWN_HANDLE))]
    top_sounds = [dict(r) for r in conn.execute(
        """SELECT sound_name, COUNT(*) uses, CAST(AVG(views) AS INTEGER) avg_views
           FROM competitor_videos
           WHERE snap_date >= ? AND handle != ? AND sound_name != ''
           GROUP BY sound_name HAVING uses >= 1
           ORDER BY avg_views DESC LIMIT 5""", (since, lib.OWN_HANDLE))]
    tag_stats: dict[str, list[int]] = {}
    for r in conn.execute(
            """SELECT hashtags_json, views FROM competitor_videos
               WHERE snap_date >= ? AND handle != ?""", (since, lib.OWN_HANDLE)):
        try:
            tags = json.loads(r["hashtags_json"] or "[]")
        except (ValueError, TypeError):
            continue
        for t in tags:
            if t:
                tag_stats.setdefault(t, []).append(r["views"] or 0)
    top_tags = sorted(
        ({"tag": k, "uses": len(v), "avg_views": int(sum(v) / len(v))}
         for k, v in tag_stats.items() if len(v) >= 2),
        key=lambda x: x["avg_views"], reverse=True)[:6]
    burn = []
    if burn_jsonl().exists():
        try:
            for line in burn_jsonl().read_text(encoding="utf-8").strip().splitlines()[-20:]:
                try:
                    burn.append(json.loads(line))
                except ValueError:
                    continue
        except OSError:
            pass
    return {
        "today": local_today().isoformat(),
        "own": own_performance(conn, days),
        "delta_1d": views_delta(conn, 1),
        "delta_7d": views_delta(conn, 7),
        "comp_daily": comp_daily,
        "comp_videos": comp_videos,
        "top_sounds": top_sounds,
        "top_tags": top_tags,
        "gap": rival_gap(conn),
        "burn": burn,
        "stock": scan_stock(),
    }


# -------------------------------------------------------------------- AI ----

def call_ai(prompt: str, system: str) -> str | None:
    if not lib.cfg("ai", "enable_ai", default=True):
        print("[growth] ai.enable_ai=false, skipping AI")
        return None
    api_key = lib.cfg("ai", "api_key", default="") or os.environ.get("AI_API_KEY")
    if not api_key:
        print("[growth] No AI_API_KEY set, skipping AI")
        return None
    base = lib.cfg("ai", "base_url", default="https://api.iamhc.cn/v1")
    model = lib.cfg("ai", "model", default="auto")
    timeout = lib.cfg("ai", "timeout_seconds", default=45)
    retries = lib.cfg("ai", "retries", default=2)
    try:
        import requests
    except ImportError:
        print("[growth] requests not installed, skipping AI")
        return None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json"},
                json={"model": model,
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": prompt}],
                      "temperature": 0.85, "max_tokens": 900},
                timeout=timeout)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            print(f"[growth] AI HTTP {resp.status_code} (try {attempt}): {resp.text[:200]}")
            if 400 <= resp.status_code < 500 and resp.status_code != 429:
                return None
        except Exception as e:
            print(f"[growth] AI call failed (try {attempt}): {e}")
    return None


def _extract_json(raw: str):
    if not raw:
        return None
    text = raw.strip()
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            candidate = part[4:] if part.lower().startswith("json") else part
            candidate = candidate.strip()
            if candidate.startswith("{"):
                text = candidate
                break
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except ValueError:
        return None


def enforce_policy(captions: list) -> tuple[list, list]:
    kept, rejected = [], []
    for cap in captions:
        report = scan_caption(cap)
        if report["needs_rewrite"]:
            reasons = [w for _, w in report["prohibited"]]
            if all(w.startswith("medical") for w in reasons):
                repaired, _notes = soften_claims(cap)
                if not scan_caption(repaired)["needs_rewrite"]:
                    cap = repaired
                    report = scan_caption(cap)
                else:
                    rejected.append(f"{cap[:48]!r} ({reasons[0]})")
                    continue
            else:
                rejected.append(f"{cap[:48]!r} ({reasons[0]})")
                continue
        out = soften(cap, rate=0.7) if report["needs_obfuscation"] else cap
        if is_too_long(out):
            out = shorten(out)
        kept.append(out)
    return kept, rejected


def build_prompt(a: dict) -> str:
    own = "\n".join(
        f"- {r['product_folder']}: avg {human(r['avg_views'])} views, "
        f"{r['uploads']} video, engage {r['engage_pct'] or 0}%"
        for r in a["own"][:6]) or "(belum ada data metrik sendiri)"
    rival = "\n".join(
        f"- @{r['handle']}: {human(r['views'])} views | sound: {r['sound_name']} "
        f"| caption: {(r['caption'] or '')[:80]}"
        for r in a["comp_videos"][:6]) or f"- @{lib.RIVAL_HANDLE}: hook viral + beg kuning + FOMO"
    sounds = ", ".join(f"{s['sound_name']} ({human(s['avg_views'])} avg)"
                       for s in a["top_sounds"]) or "-"
    tags = ", ".join(f"#{t['tag']} ({human(t['avg_views'])} avg)"
                     for t in a["top_tags"]) or "-"
    stock = ", ".join(f"{k}:{v}" for k, v in sorted(a["stock"].items(),
                                                    key=lambda x: x[1])) or "-"
    gap_line = "(tiada data pesaing)"
    if a["gap"]:
        g = a["gap"]
        gap_line = (f"@{g['own_handle']} {human(g['own_views'])} vs "
                    f"@{g['rival_handle']} {human(g['rival_views'])} -> "
                    + (f"kita ketinggalan {human(g['gap'])} views"
                       if g["behind"] else f"kita DEPAN {human(-g['gap'])} views"))
    recent = ", ".join(str(b.get("overlay_caption", ""))[:40] for b in a["burn"][-8:]) or "-"
    return f"""Kamu growth hacker TikTok Shop Malaysia untuk @{lib.OWN_HANDLE}, sasaran kalahkan @{lib.RIVAL_HANDLE}.

DATA SEBENAR HARI INI ({a['today']}):
Stok produk: {stock}
Pertumbuhan views 24 jam: {human(a['delta_1d'])} | 7 hari: {human(a['delta_7d'])}
Jurang vs pesaing: {gap_line}

PRESTASI PRODUK KAMI (7 hari):
{own}

KONTEN VIRAL PESAING (7 hari):
{rival}

Sound terbaik pesaing: {sounds}
Hashtag terbaik pesaing: {tags}

Caption yang BARU kami guna (jangan ulang gaya ini): {recent}

TUGAS:
1. Analisa ringkas: apa yang menjadi vs tidak menjadi, rujuk angka di atas.
2. Cadang produk mana nak push (pilih dari stok yang ada dan prestasi tinggi).
3. Cadang sound + hashtag.
4. Tulis 10 caption overlay BARU, Bahasa Melayu rojak:
   - 6-12 perkataan, MAKSIMUM {MAX_CAPTION_CHARS} aksara, 1-2 baris pendek
   - 1-3 emoji
   - ada FOMO/diskaun (mughrahh, hrga jatuh, stok tinggal sikit)
   - JANGAN sebut harga dalam nombor (RM39, 39 ringgit) - dilarang
   - hook mesti berbeza-beza, jangan ulang caption lama di atas
   - tanpa hashtag
{AI_CAPTION_RULES}
Balas JSON sahaja:
{{"analysis":"...","recommend_product":"...","recommend_sound":"...","recommend_hashtag":"#...","new_captions":["...","..."]}}"""


def ai_recommendations(a: dict):
    system = ("You are a TikTok Shop Malaysia growth expert fluent in Malay rojak. "
              "You respect TikTok content policy: never make medical, curative or "
              "guaranteed-result claims. You always reply with a single valid JSON "
              "object and nothing else.")
    raw = call_ai(build_prompt(a), system)
    data = _extract_json(raw) if raw else None
    if not data:
        if raw:
            print(f"[growth] Could not parse AI JSON. Raw head: {raw[:200]}")
        return None
    caps = [str(c).strip() for c in (data.get("new_captions") or []) if str(c).strip()]
    caps, rejected = enforce_policy(caps)
    for r in rejected:
        print(f"[growth] REJECTED caption - {r}")
    data["new_captions"] = caps
    if not caps:
        print("[growth] AI returned no usable captions, treating as failure")
        return None
    return data


FALLBACK_POOL = [
    "tiba tiba jatuh teruk 😭 beg kuning bawah",
    "eh murah gila hari ni, aku pun terkejut 🔥",
    "seller salah harga ke? cepat checkout 🛒",
    "penyesalan kalau tak grab sekarang 💔 stok sikit",
    "baru niat nak jimat, terus ada diskaun kaw kaw 😭👇",
    "harga budak sekolah pulak dah, gila murah ✨",
    "rupanya tengah sale besar, patut la ramai borong 🛒",
    "jujur cakap ni paling murah aku pernah jumpa 🥹",
    "kenapa baru tau? patut la viral semalam 😭",
    "tap beg kuning cepat, esok harga naik balik",
    "stok tinggal sikit je ni, jangan menyesal 😮‍💨",
    "aku dah beli tiga, memang berbaloi 🔥",
]


def fallback(a: dict) -> dict:
    if a["own"]:
        best = a["own"][0]["product_folder"]
    elif a["stock"]:
        best = max(a["stock"].items(), key=lambda x: x[1])[0]
    else:
        best = ""
    sound = a["top_sounds"][0]["sound_name"] if a["top_sounds"] else "trending viral TikTok Malaysia"
    tag = f"#{a['top_tags'][0]['tag']}" if a["top_tags"] else "#begkuning"
    return {
        "analysis": "AI offline - guna rotasi template dan pilihan berdasarkan data DB.",
        "recommend_product": best,
        "recommend_sound": sound,
        "recommend_hashtag": tag,
        "new_captions": enforce_policy(random.sample(FALLBACK_POOL, 6))[0],
        "_fallback": True,
    }


# ---------------------------------------------------------- caption pool ----

def read_pool() -> list:
    path = lib.preset_txt()
    if not path.exists():
        return []
    try:
        return [c.strip() for c in path.read_text(encoding="utf-8").split("---") if c.strip()]
    except OSError:
        return []


def update_preset_pool(new_captions: list) -> tuple[int, int]:
    existing = read_pool()
    if not new_captions:
        return 0, len(existing)
    seen = {dedup_key(c) for c in existing}
    added = 0
    for cap in new_captions:
        cap = cap.strip()
        key = dedup_key(cap)
        if key and key not in seen:
            existing.append(cap)
            seen.add(key)
            added += 1
    if len(existing) > PRESET_MAX:
        existing = existing[-PRESET_MAX:]
    try:
        lib.preset_txt().parent.mkdir(parents=True, exist_ok=True)
        lib.preset_txt().write_text("\n---\n".join(existing) + "\n", encoding="utf-8")
    except OSError as e:
        print(f"[growth] Could not write preset_text.txt: {e}")
        return 0, len(existing)
    return added, len(existing)


# --------------------------------------------------------------- reports ----

def write_reports(a: dict, ai: dict) -> str:
    L = [f"📈 TikTokFlow Growth - {stamp()}", "=" * 46, ""]
    L.append("📊 MOMENTUM:")
    L.append(f"  Views 24h: {human(a['delta_1d'])}   |   7d: {human(a['delta_7d'])}")
    L.append("")
    L.append("🎯 VS RIVAL:")
    g = a["gap"]
    if g:
        L.append(f"  @{g['own_handle']}: {human(g['own_views'])} top views")
        L.append(f"  @{g['rival_handle']}: {human(g['rival_views'])} top views")
        L.append(f"  {'BEHIND by' if g['behind'] else 'AHEAD by'} {human(abs(g['gap']))} views")
        if g["stale"]:
            L.append(f"  ⚠️ data from {g['own_date']}, scrape may have failed today")
    else:
        L.append("  (no competitor snapshot yet - run competitor_scraper.py)")
    L.append("")
    if a["stock"]:
        ok = sorted((p for p, c in a["stock"].items() if c >= 5))
        low_n = len(a["stock"]) - len(ok)
        if ok:
            shown = ", ".join(ok[:6]) + (f" +{len(ok) - 6} more" if len(ok) > 6 else "")
            L.append(f"📦 CAN PUSH ({len(ok)}/{len(a['stock'])} stocked): {shown}")
        else:
            L.append(f"📦 CANNOT PUSH: all {len(a['stock'])} products under 5 raw")
        if low_n:
            L.append(f"   {low_n} folder(s) too low - see the /sync stock list")
    else:
        L.append("📦 STOCK: (no product folders found)")
    L.append("")
    L.append("🏅 OWN 7D PERFORMANCE:")
    if a["own"]:
        for r in a["own"][:6]:
            L.append(f"  {r['product_folder']}: avg {human(r['avg_views'])} | "
                     f"best {human(r['best_views'])} | {r['uploads']} vids | "
                     f"engage {r['engage_pct'] or 0}%")
        if len(a["own"]) > 1:
            worst = a["own"][-1]
            L.append(f"  ⚠️ weakest: {worst['product_folder']} "
                     f"(avg {human(worst['avg_views'])}) - consider pausing")
    else:
        L.append("  (no metrics yet - run reconcile_metrics.py after a scrape)")
    L.append("")
    L.append("🏆 RIVAL TOP 3 (7D):")
    for i, v in enumerate(a["comp_videos"][:3], 1):
        L.append(f"  {i}. @{v['handle']} {human(v['views'])} views | {v['sound_name']}")
        L.append(f"     {(v['caption'] or '')[:70]}")
    if not a["comp_videos"]:
        L.append("  (no rival videos scraped yet)")
    L.append("")
    if a["top_tags"]:
        L.append("🔖 RIVAL BEST HASHTAGS: " +
                 ", ".join(f"#{t['tag']}({human(t['avg_views'])}" + ")" for t in a["top_tags"][:5]))
        L.append("")
    if ai.get("_cached"):
        tag = f"🤖 AI ANALYSIS (cached from {ai.get('_cached_at', 'earlier today')}):"
    elif ai.get("_fallback"):
        tag = "🤖 FALLBACK (no AI this run):"
    else:
        tag = "🤖 AI ANALYSIS (fresh):"
    L.append(tag)
    L.append("  " + (ai.get("analysis", "") or "")[:700])
    L.append("")
    L.append(f"💡 NEXT: {ai.get('recommend_product')} | sound: {ai.get('recommend_sound')} "
             f"| tag: {ai.get('recommend_hashtag')}")
    L.append("")
    caps = ai.get("new_captions", [])
    added, pool = ai.get("_added"), ai.get("_pool")
    if ai.get("_cached"):
        head = f"✨ CAPTIONS: unchanged, pool {pool} (added on the first run today)"
    elif added is None:
        head = f"✨ CAPTIONS ({len(caps)} generated):"
    elif added:
        head = f"✨ CAPTIONS: +{added} new of {len(caps)} → pool {pool}"
    else:
        head = f"✨ CAPTIONS: none new ({len(caps)} were duplicates) → pool {pool}"
    L.append(head)
    for cap in caps[:3]:
        L.append(f"  - {cap}")
    if len(caps) > 3:
        L.append(f"  … +{len(caps) - 3} more in preset_text.txt")
    report = "\n".join(L)
    try:
        lib.growth_report().parent.mkdir(parents=True, exist_ok=True)
        lib.growth_report().write_text(report, encoding="utf-8")
    except OSError as e:
        print(f"[growth] Could not write growth_report.txt: {e}")
    print(report)
    return report


def cached_ai_today(conn) -> dict | None:
    row = conn.execute(
        """SELECT best_product, best_sound_name, best_hashtag, notes, ai_called_at
           FROM daily_summary WHERE snap_date = ?""",
        (local_today().isoformat(),)).fetchone()
    if not row or not (row["ai_called_at"] or "").strip():
        return None
    return {
        "analysis": row["notes"] or "",
        "recommend_product": row["best_product"] or "",
        "recommend_sound": row["best_sound_name"] or "",
        "recommend_hashtag": row["best_hashtag"] or "",
        "new_captions": [],
        "_cached": True,
        "_cached_at": row["ai_called_at"],
    }


def resolve_recommendation(conn, a: dict, want_ai: bool) -> dict:
    if not want_ai:
        print("[growth] AI not requested (--ai absent), using local fallback")
        return fallback(a)
    cached = cached_ai_today(conn)
    if cached:
        print(f"[growth] reusing today's AI analysis from {cached['_cached_at']} "
              f"(one paid call per day)")
        return cached
    ai = ai_recommendations(a)
    if ai:
        return ai
    print("[growth] AI unavailable, using local fallback (will retry next /growth)")
    return fallback(a)


def main() -> int:
    ap = argparse.ArgumentParser(description="Growth engine. Free unless --ai.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Analyse only, write nothing (never calls AI)")
    ap.add_argument("--ai", action="store_true",
                    help="Allow ONE paid AI call per day (used by /growth)")
    ap.add_argument("--no-ai", action="store_true",
                    help="Explicitly disable AI (default)")
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()

    conn = lib.get_conn()
    lib.ensure_schema(conn)
    a = analyze(conn, args.days)
    want_ai = args.ai and not args.no_ai and not args.dry_run
    if args.ai and args.dry_run:
        print("[growth] --dry-run ignores --ai (nothing is persisted, so the "
              "call could not be cached)")
    ai = resolve_recommendation(conn, a, want_ai)

    if not args.dry_run:
        added, pool_size = update_preset_pool(ai.get("new_captions", []))
        ai["_added"], ai["_pool"] = added, pool_size
        try:
            best = ai.get("recommend_product") or (a["own"][0]["product_folder"] if a["own"] else "")
            gap_val = a["gap"]["gap"] if a["gap"] else 0
            paid_now = not ai.get("_fallback") and not ai.get("_cached")
            keeps_ai = paid_now or ai.get("_cached") or not cached_ai_today(conn)
            conn.execute("""
                INSERT INTO daily_summary(snap_date,best_product,best_sound_name,
                    best_hashtag,total_views,total_uploads,competitor_gap,notes,
                    ai_called_at)
                VALUES(:snap_date,:best_product,:best_sound,:best_hashtag,
                       :total_views,:total_uploads,:gap,:notes,:ai_called_at)
                ON CONFLICT(snap_date) DO UPDATE SET
                    best_product=CASE WHEN :keeps_ai THEN excluded.best_product
                                      ELSE daily_summary.best_product END,
                    best_sound_name=CASE WHEN :keeps_ai THEN excluded.best_sound_name
                                         ELSE daily_summary.best_sound_name END,
                    best_hashtag=CASE WHEN :keeps_ai THEN excluded.best_hashtag
                                      ELSE daily_summary.best_hashtag END,
                    notes=CASE WHEN :keeps_ai THEN excluded.notes
                               ELSE daily_summary.notes END,
                    total_views=excluded.total_views,
                    total_uploads=excluded.total_uploads,
                    competitor_gap=excluded.competitor_gap,
                    ai_called_at=COALESCE(excluded.ai_called_at,
                                          daily_summary.ai_called_at)
            """, {
                "snap_date": a["today"],
                "best_product": best,
                "best_sound": ai.get("recommend_sound", ""),
                "best_hashtag": ai.get("recommend_hashtag", ""),
                "total_views": sum(r["sum_views"] or 0 for r in a["own"]),
                "total_uploads": sum(r["uploads"] or 0 for r in a["own"]),
                "gap": gap_val,
                "notes": (ai.get("analysis", "") or "")[:1000],
                "ai_called_at": (local_now().isoformat(timespec="seconds")
                                 if paid_now else None),
                "keeps_ai": 1 if keeps_ai else 0,
            })
            conn.commit()
        except Exception as e:
            print(f"[growth] daily_summary update failed: {e}")

    write_reports(a, ai)
    conn.close()
    print("[growth] done")
    return 0


if __name__ == "__main__":
    sys.exit(main())


# =============================================================================
# Telegram Bot Compatible Interface
# =============================================================================

class AIGrowthEngine:
    """AI Growth Engine with cached daily budget - compatible with telegram_bot interface."""
    
    def __init__(self, config: dict, db: Database):
        self.config = config
        self.db = db
        self.ai_config = config.get("ai", {})
    
    def generate_captions(self, product_name: str, product_config: dict) -> list[str]:
        """Generate captions for a product using cached AI."""
        conn = lib.get_conn()
        lib.ensure_schema(conn)
        a = analyze(conn, days=7)
        conn.close()
        
        # Use cached AI if available and requested
        ai = resolve_recommendation(
            lib.get_conn(), a, want_ai=True
        )
        
        # Filter captions for this product (ai_growth generates for all products)
        # For now, return all new captions - they'll be filtered by the caller
        return ai.get("new_captions", [])
    
    def generate_strategy(self, products_config: dict) -> str | None:
        """Generate strategy report using cached AI."""
        conn = lib.get_conn()
        lib.ensure_schema(conn)
        a = analyze(conn, days=7)
        conn.close()
        
        ai = resolve_recommendation(
            lib.get_conn(), a, want_ai=True
        )
        
        if ai.get("_fallback"):
            return ai.get("analysis")
        
        # Build strategy report from AI response
        lines = [f"## Growth Strategy for @{lib.OWN_HANDLE}"]
        lines.append(f"**Analysis**: {ai.get('analysis', '')}")
        lines.append(f"**Recommended Product**: {ai.get('recommend_product', '')}")
        lines.append(f"**Recommended Sound**: {ai.get('recommend_sound', '')}")
        lines.append(f"**Recommended Hashtag**: {ai.get('recommend_hashtag', '')}")
        return "\n".join(lines)
