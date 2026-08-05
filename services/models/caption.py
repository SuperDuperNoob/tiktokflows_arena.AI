"""Caption domain model."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any


class CaptionSource(Enum):
    """Source of a caption."""
    MANUAL = "manual"
    AI_GENERATED = "ai_generated"
    COMPETITOR_INSPIRED = "competitor_inspired"


@dataclass
class Caption:
    """Represents a caption in the pool."""
    id: Optional[int] = None
    product_name: Optional[str] = None  # None = generic
    caption_text: str = ""
    description_text: Optional[str] = None
    product_tag_text: Optional[str] = None
    compliance_checked: bool = False
    times_used: int = 0
    last_used: Optional[datetime] = None
    source: CaptionSource = CaptionSource.MANUAL
    original_text: Optional[str] = None  # if rewritten
    created_at: datetime = field(default_factory=lambda: datetime.utcnow())
    updated_at: datetime = field(default_factory=lambda: datetime.utcnow())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "product_name": self.product_name,
            "caption_text": self.caption_text,
            "description_text": self.description_text,
            "product_tag_text": self.product_tag_text,
            "compliance_checked": self.compliance_checked,
            "times_used": self.times_used,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "source": self.source.value,
            "original_text": self.original_text,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Caption":
        """Create Caption from dictionary."""
        source = data.get("source", "manual")
        if isinstance(source, str):
            source = CaptionSource(source)
        
        return cls(
            id=data.get("id"),
            product_name=data.get("product_name"),
            caption_text=data.get("caption_text", ""),
            description_text=data.get("description_text"),
            product_tag_text=data.get("product_tag_text"),
            compliance_checked=data.get("compliance_checked", False),
            times_used=data.get("times_used", 0),
            last_used=datetime.fromisoformat(data["last_used"]) if data.get("last_used") else None,
            source=source,
            original_text=data.get("original_text"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.utcnow(),
            metadata=data.get("metadata", {}),
        )