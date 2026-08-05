"""Product domain model."""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class Product:
    """Represents a TikTok Shop product."""
    name: str = ""
    product_id: str = ""
    titles: List[str] = field(default_factory=list)
    captions: List[str] = field(default_factory=list)
    description: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    yellow_bag_tags: List[str] = field(default_factory=list)
    stock_count: int = 0
    raw_dir: Optional[str] = None
    processed_dir: Optional[str] = None
    posted_dir: Optional[str] = None
    failed_dir: Optional[str] = None
    stop_post: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "product_id": self.product_id,
            "titles": self.titles,
            "captions": self.captions,
            "description": self.description,
            "keywords": self.keywords,
            "yellow_bag_tags": self.yellow_bag_tags,
            "stock_count": self.stock_count,
            "raw_dir": self.raw_dir,
            "processed_dir": self.processed_dir,
            "posted_dir": self.posted_dir,
            "failed_dir": self.failed_dir,
            "stop_post": self.stop_post,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Product":
        """Create Product from dictionary."""
        return cls(
            name=data.get("name", ""),
            product_id=data.get("product_id", ""),
            titles=data.get("titles", []),
            captions=data.get("captions", []),
            description=data.get("description"),
            keywords=data.get("keywords", []),
            yellow_bag_tags=data.get("yellow_bag_tags", []),
            stock_count=data.get("stock_count", 0),
            raw_dir=data.get("raw_dir"),
            processed_dir=data.get("processed_dir"),
            posted_dir=data.get("posted_dir"),
            failed_dir=data.get("failed_dir"),
            stop_post=data.get("stop_post", False),
            metadata=data.get("metadata", {}),
        )