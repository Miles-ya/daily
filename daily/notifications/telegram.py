from __future__ import annotations

import os

from daily.notifications.base import NotificationProvider


class TelegramNotification(NotificationProvider):
    """V1 safety stub. Sending is deliberately disabled until the notification phase."""

    def __init__(self):
        self.enabled = os.getenv("ENABLE_TELEGRAM", "false").lower() == "true"
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")

    def send_digest(self, digest: dict) -> bool:
        if not self.enabled or not self.token or not self.chat_id:
            return False
        return False
