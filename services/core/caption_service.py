"""Caption service for managing caption pool."""

from typing import Any, Dict, List, Optional
from datetime import datetime

from services.repositories import CaptionRepository
from services.models import Caption, CaptionSource


class CaptionService:
    """Service for caption pool management."""

    def __init__(self):
        self.caption_repo = CaptionRepository()

    def add_caption(self, product_name: Optional[str], caption_text: str,
                    description_text: Optional[str] = None,
                    product_tag_text: Optional[str] = None,
                    source: CaptionSource = CaptionSource.MANUAL,
                    compliance_checked: bool = False,
                    original_text: Optional[str] = None) -> Caption:
        """Add a caption to the pool."""
        caption = Caption(
            product_name=product_name,
            caption_text=caption_text,
            description_text=description_text,
            product_tag_text=product_tag_text,
            compliance_checked=compliance_checked,
            source=source,
            original_text=original_text,
        )
        caption_id = self.caption_repo.create(caption)
        caption.id = caption_id
        return caption

    def get_available_captions(self, product_name: str, limit: int = 10) -> List[Caption]:
        """Get available captions for a product."""
        return self.caption_repo.get_by_product(product_name, limit)

    def get_all_for_product(self, product_name: str) -> List[Caption]:
        """Get all captions for a product."""
        return self.caption_repo.get_all_for_product(product_name)

    def mark_used(self, caption_id: int) -> None:
        """Mark a caption as used."""
        self.caption_repo.mark_used(caption_id)

    def get_stats(self) -> Dict[str, Any]:
        """Get caption pool statistics."""
        return {"total": 0, "compliant": 0, "by_product": {}}