"""Telegram adapter for bot interactions."""

from typing import Any, Dict, List, Optional
from services.infrastructure.config import get_config


class TelegramAdapter:
    """Adapter for Telegram bot interactions."""

    def __init__(self):
        self.config = get_config()

    def send_message(self, text: str, chat_id: Optional[int] = None) -> bool:
        """Send a message via Telegram."""
        return False

    def send_photo(self, photo_path: str, caption: str, chat_id: Optional[int] = None) -> bool:
        """Send a photo via Telegram."""
        return False

    def send_notification(self, message: str) -> bool:
        """Send a notification to the configured user."""
        return False

    def notify_upload_success(self, product_name: str, caption: str,
                              stock_report: Dict[str, Any],
                              posts_today: int, target: int) -> bool:
        """Send upload success notification."""
        return False

    def notify_upload_failure(self, product_name: str, error_msg: str,
                              video_path: str, will_retry: bool) -> bool:
        """Send upload failure notification."""
        return False

    def notify_warning(self, warning_type: str, message: str) -> bool:
        """Send warning notification."""
        return False