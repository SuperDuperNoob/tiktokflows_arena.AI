"""AI adapter for AI-powered features."""

from typing import Any, Dict, List, Optional, Tuple
import requests
import json
import random
import time
from datetime import date, datetime, timedelta, timezone

from services.infrastructure.config import get_config
from services.utils.db_utils import get_conn, ensure_schema
from services.utils.timezone import local_today, local_now, OWN_HANDLE, RIVAL_HANDLE
from services.infrastructure.logging import get_logger

import sys
import os
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "scripts")
sys.path.insert(0, SCRIPTS_DIR)

logger = get_logger("ai_adapter")


class AIAdapter:
    """Adapter for AI-powered features."""

    def __init__(self):
        self.config = get_config()
        self.ai_config = self.config.get_section("ai")

    # --------------------------- AI Core ------------------------------------

    def _ai_available(self) -> bool:
        return bool(
            self.ai_config.get("enable_ai", False)
            and self.ai_config.get("api_key")
            and self.ai_config.get("base_url")
        )

    def call_ai(self, prompt: str, system: str, model: Optional[str] = None,
                max_tokens: int = 1000, temperature: float = 0.7,
                retries: Optional[int] = None) -> Optional[str]:
        """Call the AI API with retries."""
        if not self._ai_available():
            return None

        base = self.ai_config.get("base_url", "").rstrip("/")
        api_key = self.ai_config.get("api_key", "")
        model = model or self.ai_config.get("model", "auto")
        timeout = self.ai_config.get("timeout_seconds", 45)
        retries = retries or self.ai_config.get("retries", 2)

        for attempt in range(1, retries + 1):
            try:
                resp = requests.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}",
                             "Content-Type": "application/json"},
                    json={"model": model,
                          "messages": [{"role": "system", "content": system},
                                       {"role": "user", "content": prompt}],
                          "temperature": temperature,
                          "max_tokens": max_tokens},
                    timeout=timeout)
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"]
                if 400 <= resp.status_code < 500 and resp.status_code != 429:
                    return None
            except Exception as e:
                logger.debug("AI call failed (attempt %d): %s", attempt, e)
        return None

    # --------------------------- Daily Budget Gate --------------------------

    def _cached_ai_today(self) -> Optional[Dict[str, Any]]:
        """Check if AI was already called today (business timezone)."""
        conn = get_conn()
        ensure_schema(conn)
        row = conn.execute(
            """SELECT best_product, best_sound_name, best_hashtag, notes, ai_called_at
               FROM daily_summary WHERE snap_date = ?""",
            (local_today().isoformat(),)).fetchone()
        conn.close()
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

    def _save_ai_call(self, ai_result: Dict[str, Any], analysis_data: Dict[str, Any],
                      paid_now: bool) -> None:
        """Save AI call result to daily_summary with budget tracking."""
        conn = get_conn()
        ensure_schema(conn)
        a = analysis_data
        gap_val = a["gap"]["gap"] if a["gap"] else 0
        paid_now_flag = not ai_result.get("_fallback") and not ai_result.get("_cached")
        keeps_ai = paid_now_flag or ai_result.get("_cached") or not self._cached_ai_today()
        try:
            conn.execute("""\n                INSERT INTO daily_summary(snap_date,best_product,best_sound_name,\n                    best_hashtag,total_views,total_uploads,competitor_gap,notes,\n                    ai_called_at)\n                VALUES(:snap_date,:best_product,:best_sound,:best_hashtag,\n                       :total_views,:total_uploads,:gap,:notes,:ai_called_at)\n                ON CONFLICT(snap_date) DO UPDATE SET\n                    best_product=CASE WHEN :keeps_ai THEN excluded.best_product\n                                     ELSE daily_summary.best_product END,\n                    best_sound_name=CASE WHEN :keeps_ai THEN excluded.best_sound_name\n                                     ELSE daily_summary.best_sound_name END,\n                    best_hashtag=CASE WHEN :keeps_ai THEN excluded.best_hashtag\n                                     ELSE daily_summary.best_hashtag END,\n                    notes=CASE WHEN :keeps_ai THEN excluded.notes\n                              ELSE daily_summary.notes END,\n                    ai_called_at=CASE WHEN :keeps_ai THEN excluded.ai_called_at\n                                     ELSE daily_summary.ai_called_at END\n                """,
                {"snap_date": local_today().isoformat(),
                 "best_product": ai_result.get("recommend_product", ""),
                 "best_sound": ai_result.get("recommend_sound", ""),
                 "best_hashtag": ai_result.get("recommend_hashtag", ""),
                 "total_views": 0,
                 "total_uploads": 0,
                 "gap": gap_val,
                 "notes": ai_result.get("analysis", ""),
                 "ai_called_at": local_now().isoformat() if paid_now_flag else "",
                 "keeps_ai": keeps_ai})
            conn.commit()
        except Exception as e:
            logger.warning("Failed to save AI call record: %s", e)
        finally:
            conn.close()

    # --------------------------- Growth Engine ------------------------------

    def _analyze(self, days: int = 7) -> Dict[str, Any]:
        """Analyze competitor and own data for growth engine."""
        since = (local_today() - timedelta(days=days)).isoformat()
        conn = get_conn()
        ensure_schema(conn)

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
           ORDER BY views DESC LIMIT 15""", (since, OWN_HANDLE))]

        top_sounds = [dict(r) for r in conn.execute(
            """SELECT sound_name, COUNT(*) uses, CAST(AVG(views) AS INTEGER) avg_views
               FROM competitor_videos
               WHERE snap_date >= ? AND handle != ? AND sound_name != ''
               GROUP BY sound_name HAVING uses >= 1
               ORDER BY avg_views DESC LIMIT 5""", (since, OWN_HANDLE))]

        tag_stats: Dict[str, List[int]] = {}
        for r in conn.execute(
                """SELECT hashtags_json, views FROM competitor_videos
                   WHERE snap_date >= ? AND handle != ?""", (since, OWN_HANDLE)):
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

        # Get own performance
        own = self._own_performance(conn, days)

        # Get rival gap
        gap = self._rival_gap(conn)

        conn.close()

        return {
            "today": local_today().isoformat(),
            "own": own,
            "delta_1d": self._views_delta(conn, 1) if conn else 0,
            "delta_7d": self._views_delta(conn, 7) if conn else 0,
            "comp_daily": comp_daily,
            "comp_videos": comp_videos,
            "top_sounds": top_sounds,
            "top_tags": top_tags,
            "gap": gap,
            "burn": burn,
            "stock": self._scan_stock(),
        }

    def _own_performance(self, conn, days: int = 7) -> List[Dict[str, Any]]:
        """Get own product performance."""
        since = (date.today() - timedelta(days=days)).isoformat()
        query = """\n            WITH latest AS (\n                SELECT video_id, views, likes, shares, comments, snap_date,\n                       ROW_NUMBER() OVER (\n                           PARTITION BY video_id ORDER BY snap_date DESC\n                       ) AS rn\n                FROM daily_metrics WHERE snap_date >= ?\n            )\n            SELECT COALESCE(NULLIF(v.product_folder, ''), '(unassigned)') AS product_folder,\n                   COUNT(*) AS uploads,\n                   CAST(SUM(l.views) AS INTEGER) AS sum_views,\n                   CAST(AVG(l.views) AS INTEGER) AS avg_views,\n                   MAX(l.views) AS best_views,\n                   CAST(SUM(l.likes) AS INTEGER) AS sum_likes,\n                   ROUND(100.0 * SUM(l.likes) / NULLIF(SUM(l.views), 0), 2) AS engage_pct\n            FROM latest l\n            JOIN videos v ON v.video_id = l.video_id\n            WHERE l.rn = 1\n            GROUP BY product_folder\n            ORDER BY avg_views DESC\n        """
        rows = conn.execute(query, (since,)).fetchall()
        return [dict(r) for r in rows]

    def _views_delta(self, conn, days: int) -> int:
        """Get views delta over specified days."""
        today = date.today().isoformat()
        prior = (date.today() - timedelta(days=days)).isoformat()
        query = """\n            WITH snap AS (\n                SELECT video_id, views,\n                       ROW_NUMBER() OVER (PARTITION BY video_id ORDER BY snap_date DESC) rn\n                FROM daily_metrics WHERE snap_date <= ?\n            ), older AS (\n                SELECT video_id, views,\n                       ROW_NUMBER() OVER (PARTITION BY video_id ORDER BY snap_date DESC) rn\n                FROM daily_metrics WHERE snap_date <= ?\n            )\n            SELECT COALESCE(SUM(s.views), 0) - COALESCE(SUM(o.views), 0) AS delta\n            FROM snap s LEFT JOIN older o ON o.video_id = s.video_id AND o.rn = 1\n            WHERE s.rn = 1\n        """
        row = conn.execute(query, (today, prior)).fetchone()
        return int(row["delta"] or 0) if row else 0

    def _rival_gap(self, conn) -> Optional[Dict[str, Any]]:
        """Get gap between own and rival performance."""
        query = """\n            SELECT handle, snap_date, followers, posts_today,\n                   top_sound_name, top_hashtag, top_views\n            FROM competitor_daily\n            WHERE handle IN (?, ?)\n            ORDER BY snap_date DESC\n        """
        rows = conn.execute(query, (OWN_HANDLE, RIVAL_HANDLE)).fetchall()
        if len(rows) < 2:
            return None

        own = rows[0] if rows[0]["handle"] == OWN_HANDLE else rows[1]
        rival = rows[1] if rows[1]["handle"] == RIVAL_HANDLE else rows[0]

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
            "stale": own.get("snap_date") != date.today().isoformat(),
        }

    def _scan_stock(self) -> Dict[str, int]:
        """Scan local stock."""
        from services.utils.stock import scan_stock
        return scan_stock()

    # --------------------------- Prompt Building ----------------------------

    def _build_prompt(self, a: Dict[str, Any]) -> str:
        """Build the AI prompt for growth engine."""
        from caption_policy import AI_CAPTION_RULES, MAX_CAPTION_CHARS
        from services.utils.timezone import human

        own = "\n".join(
            f"- {r['product_folder']}: avg {human(r['avg_views'])} views, "
            f"{r['uploads']} video, engage {r['engage_pct'] or 0}%"
            for r in a["own"][:6]) or "(belum ada data metrik sendiri)"
        rival = "\n".join(
            f"- @{r['handle']}: {human(r['views'])} views | sound: {r['sound_name']} "
            f"| caption: {(r['caption'] or '')[:80]}"
            for r in a["comp_videos"][:6]) or f"- @{RIVAL_HANDLE}: hook viral + beg kuning + FOMO"
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

        return f"""Kamu growth hacker TikTok Shop Malaysia untuk @{OWN_HANDLE}, sasaran kalahkan @{RIVAL_HANDLE}.

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
{{"analysis":"...","recommend_product":"...","recommend_sound":"...","recommend_hashtag":"#...","new_captions":["...","..."]}}
"""

    def _enforce_policy(self, captions: List[str]) -> Tuple[List[str], List[str]]:
        """Enforce caption policy on generated captions."""
        from caption_policy import (AI_CAPTION_RULES, MAX_CAPTION_CHARS, dedup_key,
                                    is_too_long, scan_caption, shorten, soften,
                                    soften_claims)
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

    def _extract_json(self, raw: str) -> Optional[Dict[str, Any]]:
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

    def _fallback(self, a: Dict[str, Any]) -> Dict[str, Any]:
        """Local fallback when AI is unavailable."""
        from caption_policy import MAX_CAPTION_CHARS
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
            "new_captions": self._enforce_policy(random.sample(FALLBACK_POOL, 6))[0],
            "_fallback": True,
        }

    # --------------------------- Public API ---------------------------------

    def generate_growth_report(self, days: int = 7, dry_run: bool = False,
                               force_ai: bool = False) -> Dict[str, Any]:
        """Generate growth report with daily AI budget enforcement."""
        a = self._analyze(days)

        # Check cache first
        cached = self._cached_ai_today()
        want_ai = force_ai and not dry_run

        if cached and not force_ai:
            logger.info("Reusing today's AI analysis from %s (one paid call per day)",
                       cached["_cached_at"])
            return cached

        if want_ai:
            ai = self._ai_recommendations(a)
            if ai:
                self._save_ai_call(ai, a, paid_now=not ai.get("_fallback"))
                return ai
            logger.warning("AI unavailable, using local fallback (will retry next call)")
            return self._fallback(a)

        return self._fallback(a)

    def _ai_recommendations(self, a: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Call AI for recommendations with policy enforcement."""
        system = ("You are a TikTok Shop Malaysia growth expert fluent in Malay rojak. "
                  "You respect TikTok content policy: never make medical, curative or "
                  "guaranteed-result claims. You always reply with a single valid JSON "
                  "object and nothing else.")
        raw = self.call_ai(self._build_prompt(a), system)
        data = self._extract_json(raw) if raw else None
        if not data:
            if raw:
                logger.warning("Could not parse AI JSON. Raw head: %s", raw[:200])
            return None

        caps = [str(c).strip() for c in (data.get("new_captions") or []) if str(c).strip()]
        caps, rejected = self._enforce_policy(caps)
        for r in rejected:
            logger.warning("REJECTED caption - %s", r)
        data["new_captions"] = caps
        if not caps:
            logger.warning("AI returned no usable captions, treating as failure")
            return None
        return data

    def generate_captions(self, product_name: str, product_config: Dict[str, Any]) -> List[str]:
        """Generate captions for a product using cached AI."""
        # Use growth engine for now - it generates for all products
        result = self.generate_growth_report(days=7, force_ai=True)
        return result.get("new_captions", [])

    def generate_strategy(self, products_config: Dict[str, Any]) -> Optional[str]:
        """Generate strategy report using cached AI."""
        result = self.generate_growth_report(days=7, force_ai=True)
        if result.get("_fallback"):
            return result.get("analysis")
        return f"""## Growth Strategy for @{OWN_HANDLE}
**Analysis**: {result.get('analysis', '')}
**Recommended Product**: {result.get('recommend_product', '')}
**Recommended Sound**: {result.get('recommend_sound', '')}
**Recommended Hashtag**: {result.get('recommend_hashtag', '')}"""

    def check_compliance(self, caption_text: str) -> Dict[str, Any]:
        """Check caption compliance using AI."""
        if not self._ai_available():
            return {"is_compliant": True, "violations": [], "severity": "none"}

        system = ("You are a TikTok Shop Malaysia compliance officer.\n"
                  "Review captions for medical claims, price guarantees, superlatives, guaranteed results.\n"
                  'Reply with ONLY JSON: {"is_compliant": bool, "violations": [...], "rewritten_caption": "..."}')

        response = self.call_ai(f'Analyze: "{caption_text}"', system, max_tokens=500, temperature=0.1)
        if not response:
            return {"is_compliant": True, "violations": [], "severity": "none"}

        try:
            start, end = response.find("{"), response.rfind("}")
            if start != -1 and end > start:
                data = json.loads(response[start:end + 1])
                return data if isinstance(data, dict) else {"is_compliant": True, "violations": []}
        except json.JSONDecodeError:
            pass
        return {"is_compliant": True, "violations": [], "severity": "none"}

    def rewrite_caption(self, caption_text: str) -> Optional[str]:
        """Rewrite a caption to be compliant."""
        result = self.check_compliance(caption_text)
        return result.get("rewritten_caption")