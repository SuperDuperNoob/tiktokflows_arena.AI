"""Compliance service for caption validation."""

from typing import Any, Dict, List, Optional

from services.repositories import CaptionRepository
from services.models import ComplianceResult
from services.infrastructure.ai_adapter import AIAdapter


class ComplianceService:
    """Service for caption compliance checking."""

    def __init__(self):
        self.caption_repo = CaptionRepository()
        self.ai_adapter = AIAdapter()

    def check_caption(self, caption_text: str) -> ComplianceResult:
        """Check a caption for compliance."""
        # This would integrate with the AI adapter and caption policy
        return ComplianceResult(
            is_compliant=True,
            final_text=caption_text,
            issues=[],
        )

    def process_caption(self, caption_text: str) -> ComplianceResult:
        """Process a caption through the full compliance pipeline."""
        return self.check_caption(caption_text)

    def validate_for_pool(self, caption_text: str) -> ComplianceResult:
        """Validate a caption for addition to the pool."""
        return self.process_caption(caption_text)

    def batch_check(self, captions: List[str]) -> List[ComplianceResult]:
        """Check multiple captions."""
        return [self.process_caption(c) for c in captions]