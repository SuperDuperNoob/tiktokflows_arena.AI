"""Compliance result domain model."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ComplianceResult:
    """Result of a compliance check."""
    is_compliant: bool
    final_text: str
    issues: List[str] = field(default_factory=list)
    original_text: str = ""
    was_rewritten: bool = False
    rewrite_notes: Optional[str] = None
    severity: str = "none"  # none, low, medium, high
    confidence: float = 1.0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "is_compliant": self.is_compliant,
            "final_text": self.final_text,
            "issues": self.issues,
            "original_text": self.original_text,
            "was_rewritten": self.was_rewritten,
            "rewrite_notes": self.rewrite_notes,
            "severity": self.severity,
            "confidence": self.confidence,
        }