"""Daily summary domain model."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class DailySummary:
    """Daily analytics summary."""
    snap_date: date
    best_product: Optional[str] = None
    best_sound_id: Optional[str] = None
    best_sound_name: Optional[str] = None
    best_hashtag: Optional[str] = None
    total_views: int = 0
    total_uploads: int = 0
    competitor_gap: int = 0
    notes: Optional[str] = None
    ai_called_at: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.utcnow())
    updated_at: datetime = field(default_factory=lambda: datetime.utcnow())

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "snap_date": self.snap_date.isoformat(),
            "best_product": self.best_product,
            "best_sound_id": self.best_sound_id,
            "best_sound_name": self.best_sound_name,
            "best_hashtag": self.best_hashtag,
            "total_views": self.total_views,
            "total_uploads": self.total_uploads,
            "competitor_gap": self.competitor_gap,
            "notes": self.notes,
            "ai_called_at": self.ai_called_at,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DailySummary":
        """Create DailySummary from dictionary."""
        return cls(
            snap_date=date.fromisoformat(data["snap_date"]),
            best_product=data.get("best_product"),
            best_sound_id=data.get("best_sound_id"),
            best_sound_name=data.get("best_sound_name"),
            best_hashtag=data.get("best_hashtag"),
            total_views=data.get("total_views", 0),
            total_uploads=data.get("total_uploads", 0),
            competitor_gap=data.get("competitor_gap", 0),
            notes=data.get("notes"),
            ai_called_at=data.get("ai_called_at"),
        )