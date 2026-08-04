"""
compliance.py - merged two-layer caption compliance engine.

Brings together the battle-tested tiktokflow_vps caption_policy.py (regex
pre-filter + phonetic obfuscation + claim repair) and tiktok-machine's
context-aware LLM checking into one pipeline:

  1. Regex pre-filter   - fast, catches the obvious (medical/price/overclaim)
  2. AI analysis        - context-aware, catches evasion + implicit claims
  3. Obfuscation layer  - phonetic disguise of hype words (murah -> mughrahh)

The two source modules disagree on one important point, and we resolve it the
production way: obfuscation is an ANTI-SPAM measure, not a compliance licence.
Medical claims, prices and absolute overclaims are still dropped/repaired by
the regex layer even when the AI would let them through.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from caption_policy import (
    MAX_CAPTION_CHARS,
    find_prohibited,
    is_too_long,
    scan_caption,
    shorten,
    soften,
    soften_claims,
)

logger = logging.getLogger(__name__)


class ComplianceEngine:
    """Two-layer caption compliance: regex + optional LLM, then obfuscation."""

    def __init__(self, config: Optional[dict] = None, ai_config: Optional[dict] = None):
        config = config or {}
        self.strict_mode = config.get("strict_mode", True)
        self.use_ai = config.get("use_ai", True)
        self.banned_phrases = [p.lower() for p in config.get("banned_phrases", [])]

        ai_config = ai_config or {}
        self.ai_api_key = ai_config.get("api_key", "")
        self.ai_base_url = (ai_config.get("base_url") or "").rstrip("/")
        self.ai_model = ai_config.get("compliance_model",
                                      ai_config.get("model", "auto"))
        self.ai_timeout = ai_config.get("timeout_seconds", 45)

    # ------------------------------------------------------------------ AI ----

    def _ai_available(self) -> bool:
        return bool(self.use_ai and self.ai_api_key and self.ai_base_url)

    def _ai_analyze(self, text: str) -> Optional[dict]:
        """Context-aware check. Returns parsed JSON or None on failure."""
        if not self._ai_available():
            return None
        try:
            import requests
            system = (
                "You are a TikTok Shop Malaysia compliance officer. Review a "
                "Bahasa Malaysia video caption. Reject medical claims, ringgit "
                "prices, unverifiable superlatives and guaranteed results, "
                "including obfuscated spellings (u.b.a.t, ub4t, muraahh). "
                'Reply with ONLY JSON: {"is_compliant": bool, "violations": '
                '["..."], "rewritten_caption": "..."}.'
            )
            resp = requests.post(
                f"{self.ai_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.ai_api_key}",
                         "Content-Type": "application/json"},
                json={"model": self.ai_model,
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": text}],
                      "temperature": 0.0, "max_tokens": 300},
                timeout=self.ai_timeout)
            if resp.status_code != 200:
                logger.warning("AI compliance HTTP %s", resp.status_code)
                return None
            raw = resp.json()["choices"][0]["message"]["content"]
            import json
            start, end = raw.find("{"), raw.rfind("}")
            if start == -1 or end <= start:
                return None
            data = json.loads(raw[start:end + 1])
            return data if isinstance(data, dict) else None
        except Exception as e:
            logger.warning("AI compliance check failed: %s", e)
            return None

    # ------------------------------------------------------------ pipeline ----

    def check_caption(self, text: str) -> Tuple[bool, List[str]]:
        """Fast regex-only gate (battle-tested caption_policy rules)."""
        if not text or not text.strip():
            return True, ["Empty caption"]
        report = scan_caption(text)
        issues: List[str] = []
        for matched, why in report["prohibited"]:
            issues.append(f"{why} (match: {matched!r})")
        for phrase in self.banned_phrases:
            if phrase and phrase in text.lower():
                issues.append(f"Banned phrase: {phrase}")
        if issues and self.strict_mode:
            return False, issues
        return not bool(issues), issues

    def _obfuscate(self, text: str) -> str:
        """Phonetic disguise of hype words, then clamp to overlay limits."""
        out = soften(text, rate=0.7)
        if is_too_long(out):
            out = shorten(out)
        return out

    def process_caption(self, text: str) -> Tuple[str, bool, List[str]]:
        """Full pipeline. Returns (final_text, is_compliant, issues)."""
        if not text or not text.strip():
            return "", True, ["Empty caption"]

        text = text.strip()
        issues: List[str] = []

        # ---- Layer 1: regex pre-filter (fast, catches the obvious) ----
        report = scan_caption(text)
        if report["needs_rewrite"]:
            reasons = [w for _, w in report["prohibited"]]
            # Medical wording can be repaired into compliant lifestyle wording.
            repairable = all(w.startswith("medical") for w in reasons)
            if repairable:
                fixed, _notes = soften_claims(text)
                if not scan_caption(fixed)["needs_rewrite"]:
                    text = fixed
                    issues.append("Repaired medical wording -> compliant")
                    repairable = True
                else:
                    repairable = False
            if not repairable:
                issues.append(f"Unrepairable claim: {reasons[0]}")
                # Price/overclaim has no compliant rewrite -> drop it.
                return self._obfuscate(text), False, issues

        # ---- Layer 2: AI context-aware check ----
        if self._ai_available():
            ai = self._ai_analyze(text)
            if ai:
                if ai.get("is_compliant") is False:
                    issues.append("AI flagged non-compliant")
                    rewritten = ai.get("rewritten_caption")
                    if rewritten and rewritten.strip():
                        # Re-gate the rewrite through the regex layer.
                        r2 = scan_caption(rewritten)
                        if not r2["needs_rewrite"]:
                            text = rewritten.strip()
                            issues.append("AI rewrite applied")
                    else:
                        return self._obfuscate(text), False, issues

        # ---- Layer 3: obfuscation ----
        text = self._obfuscate(text)
        return text, True, issues

    def validate_for_pool(self, text: str) -> Tuple[bool, str, List[str]]:
        """Gate for pool insertion: nothing enters without passing here."""
        final, ok, issues = self.process_caption(text)
        if ok:
            logger.info("Caption APPROVED for pool: %r", text[:50])
        else:
            logger.warning("Caption REJECTED from pool: %r — %s", text[:50], issues)
        return ok, final, issues

    def batch_check(self, captions: List[str]) -> List[dict]:
        results = []
        for cap in captions:
            final, ok, issues = self.process_caption(cap)
            results.append({"original": cap, "final_text": final,
                            "is_compliant": ok, "issues": issues})
        return results
