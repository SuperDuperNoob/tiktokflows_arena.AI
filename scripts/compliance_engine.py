"""
AI-Powered Caption Compliance Engine

Uses an LLM for context-aware compliance checking of Bahasa Malaysia
TikTok Shop captions. Regex is used only as a fast pre-filter.

Architecture:
  1. Regex pre-filter — catches obvious violations instantly
  2. AI analysis — understands context, intent, evasion attempts
  3. AI rewrite — fixes violations while preserving meaning + tone
  4. AI re-validation — confirms the rewritten version passes

This catches things regex cannot:
  - Context-dependent violations ("ubat gigi" is fine, "ubat untuk sembuh" is not)
  - Creative evasion ("u.b.a.t", "ub4t", "ubat²", spaced letters)
  - Implicit claims ("lepas guna ni confirm putih" = guaranteed result)
  - Tone issues (too salesy, too aggressive)
  - Nuanced regulatory violations
"""
import re
import json
import logging
from typing import Tuple, List, Optional

import httpx

logger = logging.getLogger(__name__)


# =============================================================================
# COMPLIANCE SYSTEM PROMPT
# =============================================================================

COMPLIANCE_SYSTEM_PROMPT = """You are a TikTok Shop content compliance officer for Malaysia.
You review video captions written in Bahasa Malaysia (Malaysian Malay) for regulatory compliance.

You must check captions against these rules:

## HARD BLOCKS (must reject or rewrite):

### 1. Medical/Health Claims
Words implying treatment, cure, or medical benefit:
- sembuh (cure), rawat (treat), ubat (medicine), penawar (remedy)
- anti-kanser, turunkan gula, darah tinggi, kolesterol
- Also check creative evasion: "u.b.a.t", "ub4t", "u-b-a-t", "ubat²", spaced letters

### 2. Price Guarantees
- harga terbaik, paling murah, termurah, jamin murah
- Any claim of being "the cheapest"

### 3. Superlatives
- terbaik di dunia, no.1 di malaysia, nombor satu
- "The best", "number one" claims in any language mixed in

### 4. Guaranteed Results
- jamin putih, jamin cantik, jamin kurus dalam X hari
- Any promise of specific results within a timeframe
- "Confirm putih", "mesti cantik", "100% berkesan"

### 5. Implicit Medical Claims (context-dependent)
- "hilangkan jerawat" → implies medical treatment
- "hilangkan kedutan" → anti-aging medical claim
- "buang lemak" → medical weight loss claim
- These need rewriting to softer alternatives

## SOFT RULES (apply automatically, don't reject):

### 6. Superlative Softening
- "terbaik" alone → "antara pilihan ramai"
- "paling best" → "sangat digemari"

### 7. Price Claim Softening
- "RM XX sahaja" → "berbaloi dicuba"
- Specific price mentions → general value language

## OUTPUT FORMAT:

Respond with ONLY a JSON object, no other text:
{
    "is_compliant": true/false,
    "violations": ["description of each violation found"],
    "severity": "none" | "low" | "medium" | "high",
    "rewritten_caption": "the corrected caption (only if violations found, otherwise same as input)",
    "rewrite_notes": "what was changed and why (only if rewritten)",
    "confidence": 0.0-1.0
}

If the caption is compliant:
- is_compliant: true
- violations: []
- severity: "none"
- rewritten_caption: (same as input)
- rewrite_notes: ""
- confidence: 0.95+

If violations are found:
- Provide a rewritten version that preserves the ORIGINAL INTENT and TONE
  but removes the violation
- The rewrite must still sound natural in casual Malay
- Keep hashtags intact
- Keep under 150 characters if possible
"""


class ComplianceEngine:
    """AI-powered caption compliance checker with regex pre-filter."""

    def __init__(self, config: dict, ai_config: dict = None):
        # Regex config (fast pre-filter)
        self.strict_mode = config.get("strict_mode", True)
        self.creative_misspelling = config.get("creative_misspelling", False)
        self.banned_phrases = [p.lower() for p in config.get("banned_phrases", [])]
        self.rewrite_rules = config.get("rewrite_rules", {})
        self.soft_transforms = config.get("soft_transforms", {})

        # AI config
        self.ai_config = ai_config or {}
        self.ai_base_url = self.ai_config.get("base_url", "").rstrip("/")
        self.ai_api_key = self.ai_config.get("api_key", "")
        self.ai_model = self.ai_config.get("compliance_model",
                                           self.ai_config.get("caption_model", "gpt-3.5-turbo"))
        self.ai_max_tokens = self.ai_config.get("compliance_max_tokens", 500)

        # Compile regex patterns
        self._banned_patterns = []
        for phrase in self.banned_phrases:
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            self._banned_patterns.append((phrase, pattern))

        # Evasion detection patterns
        self._evasion_patterns = [
            re.compile(r'[.\-_\s]+', re.IGNORECASE),  # separators between letters
            re.compile(r'[0-9@#$]+', re.IGNORECASE),  # character substitutions
        ]

    def check_caption(self, text: str) -> Tuple[bool, List[str]]:
        """
        Fast regex-only check. Use process_caption() for AI-powered checking.
        Returns (is_safe, issues).
        """
        issues = []
        rewritten = self._apply_rewrite_rules(text)

        for phrase, pattern in self._banned_patterns:
            if pattern.search(rewritten):
                issues.append(f"Regex match: '{phrase}'")

        if issues and self.strict_mode:
            return False, issues
        return True, issues

    def process_caption(self, text: str) -> Tuple[str, bool, List[str]]:
        """
        Full AI-powered compliance pipeline.

        Pipeline:
        1. Regex pre-filter (fast, catches obvious violations)
        2. AI analysis (context-aware, catches evasion + implicit claims)
        3. AI rewrite (if needed, preserves intent and tone)
        4. AI re-validation (confirms rewrite is clean)

        Returns:
            (final_text: str, is_compliant: bool, issues: list[str])
        """
        if not text or not text.strip():
            return "", True, ["Empty caption"]

        text = text.strip()
        all_issues = []

        # ---- Step 1: Regex pre-filter ----
        regex_safe, regex_issues = self.check_caption(text)
        if regex_issues:
            all_issues.extend(regex_issues)

        # ---- Step 2: AI analysis ----
        if self._ai_available():
            ai_result = self._ai_analyze(text)

            if ai_result:
                ai_compliant = ai_result.get("is_compliant", True)
                ai_violations = ai_result.get("violations", [])
                ai_rewritten = ai_result.get("rewritten_caption", text)
                ai_confidence = ai_result.get("confidence", 0.5)
                ai_notes = ai_result.get("rewrite_notes", "")

                if ai_violations:
                    all_issues.extend([f"AI: {v}" for v in ai_violations])

                if ai_notes:
                    all_issues.append(f"AI notes: {ai_notes}")

                if not ai_compliant and ai_rewritten:
                    # ---- Step 3: AI rewrite happened ----
                    final_text = ai_rewritten

                    # ---- Step 4: Re-validate the rewrite ----
                    recheck = self._ai_analyze(final_text)
                    if recheck and not recheck.get("is_compliant", True):
                        # Rewrite still has issues — flag it
                        remaining = recheck.get("violations", [])
                        all_issues.append(f"WARNING: Rewrite may still have issues: {remaining}")
                        # Use the rewrite anyway but flag it
                        return final_text, False, all_issues

                    logger.info(
                        f"Compliance AI rewrite (confidence={ai_confidence}): "
                        f"'{text[:50]}...' → '{final_text[:50]}...'"
                    )
                    return final_text, True, all_issues

                elif ai_compliant:
                    # AI says it's fine — use original
                    return text, True, all_issues
                else:
                    # AI says non-compliant but no rewrite provided
                    return text, False, all_issues
            else:
                # AI call failed — fall back to regex result
                logger.warning("AI compliance check failed — falling back to regex-only")
                all_issues.append("AI check unavailable — regex-only result")
                return text if regex_safe else self._regex_rewrite(text), regex_safe, all_issues
        else:
            # No AI configured — regex only
            if not regex_safe:
                rewritten = self._regex_rewrite(text)
                return rewritten, False, regex_issues
            return text, True, []

    def validate_for_pool(self, text: str) -> Tuple[bool, str, List[str]]:
        """
        Validate a caption for addition to the caption pool.
        This is the gate function — nothing enters the pool without passing here.

        Returns:
            (approved: bool, final_text: str, issues: list[str])
        """
        processed, is_compliant, issues = self.process_caption(text)

        if is_compliant:
            logger.info(f"Caption APPROVED for pool: '{text[:50]}...'")
            return True, processed, issues
        else:
            logger.warning(f"Caption REJECTED from pool: '{text[:50]}...' — {issues}")
            return False, processed, issues

    def batch_check(self, captions: List[str]) -> List[dict]:
        """
        Check multiple captions in a single AI call (more efficient).
        Returns list of {caption, original, is_compliant, issues, final_text}.
        """
        if not self._ai_available() or not captions:
            # Fall back to individual checks
            results = []
            for cap in captions:
                final, ok, issues = self.process_caption(cap)
                results.append({
                    "original": cap,
                    "final_text": final,
                    "is_compliant": ok,
                    "issues": issues,
                })
            return results

        # Batch AI call
        prompt = self._build_batch_prompt(captions)
        response = self._call_ai(
            system_prompt=COMPLIANCE_SYSTEM_PROMPT,
            user_prompt=prompt,
            max_tokens=self.ai_max_tokens * len(captions),  # more tokens for batch
        )

        if not response:
            # Fall back to individual
            return self.batch_check_fallback(captions)

        parsed = self._parse_batch_response(response, len(captions))

        results = []
        for i, cap in enumerate(captions):
            if i < len(parsed):
                item = parsed[i]
                results.append({
                    "original": cap,
                    "final_text": item.get("rewritten_caption", cap),
                    "is_compliant": item.get("is_compliant", True),
                    "issues": item.get("violations", []),
                })
            else:
                results.append({
                    "original": cap,
                    "final_text": cap,
                    "is_compliant": True,
                    "issues": ["Batch parsing incomplete — assumed compliant"],
                })

        return results

    # =========================================================================
    # AI INTEGRATION
    # =========================================================================

    def _ai_available(self) -> bool:
        """Check if AI API is configured and reachable."""
        return bool(
            self.ai_base_url
            and self.ai_api_key
            and self.ai_base_url != "https://your-openai-compatible-endpoint.com/v1"
            and self.ai_api_key != "your-api-key-here"
        )

    def _ai_analyze(self, text: str) -> Optional[dict]:
        """Call AI to analyze a single caption for compliance."""
        user_prompt = f"Analyze this caption for TikTok Shop Malaysia compliance:\n\n\"{text}\""
        response = self._call_ai(COMPLIANCE_SYSTEM_PROMPT, user_prompt, self.ai_max_tokens)

        if not response:
            return None

        return self._parse_single_response(response)

    def _call_ai(self, system_prompt: str, user_prompt: str, max_tokens: int) -> Optional[str]:
        """Call the OpenAI-compatible API."""
        url = f"{self.ai_base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.ai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.ai_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.1,  # Low temperature for compliance = more deterministic
        }

        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]

            usage = data.get("usage", {})
            logger.debug(
                f"Compliance AI call: {usage.get('total_tokens', '?')} tokens"
            )
            return content

        except httpx.HTTPStatusError as e:
            logger.error(f"Compliance AI error ({e.response.status_code}): {e.response.text[:200]}")
            return None
        except Exception as e:
            logger.error(f"Compliance AI call failed: {e}")
            return None

    def _parse_single_response(self, response: str) -> Optional[dict]:
        """Parse AI compliance response into a dict."""
        text = response.strip()

        # Remove markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:])
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        try:
            result = json.loads(text)
            if isinstance(result, dict) and "is_compliant" in result:
                return result
        except json.JSONDecodeError:
            pass

        # Try to find JSON in the text
        match = re.search(r'\{[^{}]*"is_compliant"[^{}]*\}', text, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
                return result
            except json.JSONDecodeError:
                pass

        # Try to find any JSON object
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
                return result
            except json.JSONDecodeError:
                pass

        logger.warning(f"Could not parse compliance AI response: {text[:200]}")
        return None

    def _build_batch_prompt(self, captions: List[str]) -> str:
        """Build a prompt for batch caption checking."""
        lines = [f"Analyze these {len(captions)} captions for TikTok Shop Malaysia compliance.\n"]
        lines.append("Respond with a JSON array of objects, one per caption, in the same order.\n")

        for i, cap in enumerate(captions):
            lines.append(f"Caption {i+1}: \"{cap}\"")

        lines.append("\nRespond with a JSON array: [{...}, {...}, ...]")
        return "\n".join(lines)

    def _parse_batch_response(self, response: str, expected_count: int) -> List[dict]:
        """Parse a batch compliance response."""
        text = response.strip()

        # Remove markdown
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:])
            if text.endswith("```"):
                text = text[:-3]

        try:
            results = json.loads(text)
            if isinstance(results, list):
                return results
        except json.JSONDecodeError:
            pass

        # Find JSON array
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                results = json.loads(match.group())
                if isinstance(results, list):
                    return results
            except json.JSONDecodeError:
                pass

        logger.warning(f"Could not parse batch compliance response")
        return []

    # =========================================================================
    # REGEX FALLBACK METHODS
    # =========================================================================

    def _apply_rewrite_rules(self, text: str) -> str:
        """Apply explicit rewrite rules from config."""
        result = text
        for bad, good in self.rewrite_rules.items():
            result = re.sub(re.escape(bad), good, result, flags=re.IGNORECASE)
        return result

    def _apply_soft_transforms(self, text: str) -> str:
        """Apply soft language transforms."""
        result = text
        for trigger, replacement in self.soft_transforms.items():
            result = re.sub(re.escape(trigger), replacement, result, flags=re.IGNORECASE)
        return result

    def _regex_rewrite(self, text: str) -> str:
        """Apply all regex-based rewrites (fallback when AI is unavailable)."""
        result = self._apply_rewrite_rules(text)
        result = self._apply_soft_transforms(result)

        if self.creative_misspelling:
            misspellings = {
                "BEST": "BEZT", "WOW": "WOA", "GILA": "G1LA",
                "POWER": "POWERRR", "TERBAIK": "TERB4IK",
            }
            for word, misspelling in misspellings.items():
                result = re.sub(r'\b' + word + r'\b', misspelling, result, flags=re.IGNORECASE)

        # Strip remaining banned phrases
        for phrase, pattern in self._banned_patterns:
            result = pattern.sub("", result)

        result = re.sub(r'\s+', ' ', result).strip()
        return result

    def batch_check_fallback(self, captions: List[str]) -> List[dict]:
        """Fallback batch check using regex only."""
        results = []
        for cap in captions:
            final, ok, issues = self.process_caption(cap)
            results.append({
                "original": cap,
                "final_text": final,
                "is_compliant": ok,
                "issues": issues,
            })
        return results


# =============================================================================
# Module-level convenience functions
# =============================================================================

_engine_instance = None


def get_engine(config: dict = None, ai_config: dict = None) -> ComplianceEngine:
    """Get or create the singleton compliance engine."""
    global _engine_instance
    if _engine_instance is None and config:
        _engine_instance = ComplianceEngine(config, ai_config)
    return _engine_instance


def check_caption(text: str, config: dict = None, ai_config: dict = None) -> Tuple[bool, List[str]]:
    """Fast regex-only check."""
    engine = get_engine(config, ai_config)
    return engine.check_caption(text)


def process_caption(text: str, config: dict = None, ai_config: dict = None) -> Tuple[str, bool, List[str]]:
    """Full AI-powered compliance pipeline."""
    engine = get_engine(config, ai_config)
    return engine.process_caption(text)
