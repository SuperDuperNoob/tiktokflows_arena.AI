"""Event repository for managing system events."""

from typing import Any, Dict, List, Optional
from datetime import datetime
import json

from .base import BaseRepository


class EventRepository(BaseRepository):
    """Repository for system event operations."""

    def get_table_name(self) -> str:
        return "system_events"

    def log_event(self, event_type: str, message: str, metadata: Optional[Dict[str, Any]] = None) -> int:
        """Log a system event."""
        data = {
            "event_type": event_type,
            "message": message,
            "metadata": json.dumps(metadata) if metadata else None,
        }
        return self.insert("system_events", data)

    def get_recent(self, limit: int = 20, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get recent events."""
        if event_type:
            rows = self.fetchall(
                "SELECT * FROM system_events WHERE event_type = ? ORDER BY occurred_at DESC LIMIT ?",
                (event_type, limit),
            )
        else:
            rows = self.fetchall(
                "SELECT * FROM system_events ORDER BY occurred_at DESC LIMIT ?",
                (limit,),
            )
        return rows