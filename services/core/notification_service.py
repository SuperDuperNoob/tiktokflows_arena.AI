"""Notification service for sending notifications."""

from typing import Any, Dict, List, Optional

from services.infrastructure.telegram_adapter import TelegramAdapter


class NotificationService:
    """Service for sending notifications."""

    def __init__(self):
        self.telegram = TelegramAdapter()

    def notify_upload_success(self, product_name: str, caption: str,
                              stock_report: Dict[str, Any],
                              posts_today: int, target: int) -> None:
        """Send upload success notification."""
        pass

    def notify_upload_failure(self, product_name: str, error_msg: str,
                              video_path: str, will_retry: bool) -> None:
        """Send upload failure notification."""
        pass

    def notify_warning(self, warning_type: str, message: str) -> None:
        """Send warning notification."""
        pass

    def send_status_report(self) -> None:
        """Send status report."""
        pass