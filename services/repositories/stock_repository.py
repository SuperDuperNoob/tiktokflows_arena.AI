"""Stock repository for managing raw video stock."""

from typing import Any, Dict, List, Optional
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
from config import get_config

from .base import BaseRepository


class StockRepository(BaseRepository):
    """Repository for raw stock operations."""

    def __init__(self, db_path: str):
        super().__init__(db_path)

    def get_table_name(self) -> str:
        return "raw_stock"

    def sync_stock(self, product_name: str, filenames: List[str]) -> None:
        """Sync raw stock for a product (upsert)."""
        for fname in filenames:
            self.execute(
                """INSERT OR IGNORE INTO raw_stock (product_name, filename) VALUES (?, ?)""",
                (product_name, fname),
            )

    def get_stock_counts(self) -> Dict[str, int]:
        """Get available raw video counts per product."""
        rows = self.fetchall(
            """SELECT product_name, COUNT(*) as cnt
               FROM raw_stock
               WHERE posted_at IS NULL
               GROUP BY product_name"""
        )
        return {row["product_name"]: row["cnt"] for row in rows}

    def get_unused_videos(self, product_name: str, exclude_recent: int = 5) -> List[Dict[str, Any]]:
        """Get unused raw videos for a product."""
        rows = self.fetchall(
            """SELECT * FROM raw_stock
               WHERE product_name = ? AND posted_at IS NULL
               ORDER BY last_used ASC NULLS FIRST, use_count ASC
               LIMIT 100""",
            (product_name,),
        )
        if len(rows) > exclude_recent:
            return rows[exclude_recent:]
        return rows

    def mark_used(self, stock_id: int) -> int:
        """Mark a raw video as used."""
        return self.update(
            "raw_stock",
            {"use_count": "use_count + 1", "last_used": datetime.utcnow().isoformat()},
            "id = ?",
            (stock_id,),
        )

    def mark_consumed(self, product_name: str, filename: str, file_hash: Optional[str] = None) -> int:
        """Mark a raw video as consumed (posted)."""
        return self.execute(
            """INSERT OR IGNORE INTO raw_stock(product_name, filename) VALUES (?, ?)""",
            (product_name, filename),
        ).rowcount + self.execute(
            """UPDATE raw_stock SET file_hash = COALESCE(?, file_hash),
               posted_at = COALESCE(posted_at, ?)
               WHERE product_name = ? AND filename = ?""",
            (file_hash, datetime.utcnow().isoformat(), product_name, filename),
        ).rowcount