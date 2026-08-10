"""Compliance package for TikTok caption policy."""
from .caption_policy import (
    MAX_CAPTION_CHARS,
    MAX_CAPTION_LINES,
    MAX_LINE_CHARS,
    AI_CAPTION_RULES,
    HYPE_TERMS,
    PROHIBITED_PATTERNS,
    MEDICAL_SUBSTITUTIONS,
    find_hype,
    find_prohibited,
    soften,
    dedup_key,
    shorten,
    soften_claims,
    is_too_long,
    scan_caption,
    obfuscate_word,
    obfuscate_phrase,
)

from .compliance_engine import ComplianceEngine

__all__ = [
    "MAX_CAPTION_CHARS",
    "MAX_CAPTION_LINES",
    "MAX_LINE_CHARS",
    "AI_CAPTION_RULES",
    "HYPE_TERMS",
    "PROHIBITED_PATTERNS",
    "MEDICAL_SUBSTITUTIONS",
    "find_hype",
    "find_prohibited",
    "soften",
    "dedup_key",
    "shorten",
    "soften_claims",
    "is_too_long",
    "scan_caption",
    "obfuscate_word",
    "obfuscate_phrase",
    "ComplianceEngine",
]