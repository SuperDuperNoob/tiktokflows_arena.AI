"""Growth report domain model."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional


@dataclass
class GrowthReport:
    """AI-generated growth strategy report."""
    analysis: str = ""
    recommend_product: str = ""
    recommend_sound: str = ""
    recommend_hashtag: str = ""
    new_captions: List[str] = field(default_factory=list)
    cached: bool = False
    cached_at: Optional[str] = None
    fallback: bool = False
    products_analyzed: Dict[str, Any] = field(default_factory=dict)
    competitor_gap: Optional[Dict[str, Any]] = None
    stock_levels: Dict[str, int] = field(default_factory=dict)
    top_sounds: List[Dict[str, Any]] = field(default_factory=list)
    top_hashtags: List[Dict[str, Any]] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.utcnow())

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "analysis": self.analysis,
            "recommend_product": self.recommend_product,
            "recommend_sound": self.recommend_sound,
            "recommend_hashtag": self.recommend_hashtag,
            "new_captions": self.new_captions,
            "cached": self.cached,
            "cached_at": self.cached_at,
            "fallback": self.fallback,
            "products_analyzed": self.products_analyzed,
            "competitor_gap": self.competitor_gap,
            "stock_levels": self.stock_levels,
            "top_sounds": self.top_sounds,
            "top_hashtags": self.top_hashtags,
            "generated_at": self.generated_at.isoformat(),
        }