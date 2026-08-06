"""Caption repository for managing caption pool."""

from typing import Any, Dict, List, Optional
from datetime import datetime

from .base import BaseRepository
from services.models.caption import Caption, CaptionSource


class CaptionRepository(BaseRepository):
    """Repository for caption operations."""

    def __init__(self, db_path: str):
        super().__init__(db_path)

    def get_table_name(self) -> str:
        return "caption_pool"

    def create(self, caption: Caption) -> int:
        """Create a new caption."""
        data = {
            "product_name": caption.product_name,
            "caption_text": caption.caption_text,
            "description_text": caption.description_text,
            "product_tag_text": caption.product_tag_text,
            "compliance_checked": 1 if caption.compliance_checked else 0,
            "times_used": caption.times_used,
            "last_used": caption.last_used.isoformat() if caption.last_used else None,
            "source": caption.source.value,
            "original_text": caption.original_text,
        }
        return self.insert("caption_pool", data)

    def get_by_id(self, caption_id: int) -> Optional[Caption]:
        """Get caption by ID."""
        row = self.fetchone("SELECT * FROM caption_pool WHERE id = ?", (caption_id,))
        return self._row_to_caption(row) if row else None

    def get_by_product(self, product_name: Optional[str], limit: int = 100) -> List[Caption]:
        """Get captions for a product (or all if product_name is None)."""
        if product_name:
            rows = self.fetchall(
                "SELECT * FROM caption_pool WHERE (product_name = ? OR product_name IS NULL) AND compliance_checked = 1 ORDER BY times_used ASC, last_used ASC NULLS FIRST LIMIT ?",
                (product_name, limit),
            )
        else:
            rows = self.fetchall(
                "SELECT * FROM caption_pool WHERE compliance_checked = 1 ORDER BY times_used ASC, last_used ASC NULLS FIRST LIMIT ?",
                (limit,),
            )
        return [c for c in (self._row_to_caption(row) for row in rows) if c is not None]

    def get_all_for_product(self, product_name: str) -> List[Caption]:
        """Get all captions for a product (for /captions command)."""
        rows = self.fetchall(
            "SELECT * FROM caption_pool WHERE product_name = ? OR product_name IS NULL ORDER BY times_used DESC",
            (product_name,),
        )
        return [c for c in (self._row_to_caption(row) for row in rows) if c is not None]

    def mark_used(self, caption_id: int) -> int:
        """Mark caption as used."""
        return self.update(
            "caption_pool",
            {"times_used": "times_used + 1", "last_used": datetime.utcnow().isoformat()},
            "id = ?",
            (caption_id,),
        )

    def _row_to_caption(self, row: Dict[str, Any]) -> Optional[Caption]:
        """Convert database row to Caption model."""
        if not row:
            return None
        
        source = row.get("source", "manual")
        if isinstance(source, str):
            try:
                from services.models.caption import CaptionSource
                source = CaptionSource(source)
            except ValueError:
                from services.models.caption import CaptionSource
                source = CaptionSource.MANUAL
        
        return Caption(
            id=row.get("id"),
            product_name=row.get("product_name"),
            caption_text=row.get("caption_text", ""),
            description_text=row.get("description_text"),
            product_tag_text=row.get("product_tag_text"),
            compliance_checked=bool(row.get("compliance_checked", 0)),
            times_used=row.get("times_used", 0),
            last_used=datetime.fromisoformat(row["last_used"]) if row.get("last_used") else None,
            source=source,
            original_text=row.get("original_text"),
        )