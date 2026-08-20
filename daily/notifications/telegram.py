from __future__ import annotations

import os

import requests

from daily.notifications.base import NotificationProvider


class TelegramNotification(NotificationProvider):
    """Telegram Bot API provider. Message payloads are never logged."""

    def __init__(self):
        self.enabled = os.getenv("ENABLE_TELEGRAM", "false").lower() == "true"
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")

    def send_digest(self, digest: dict) -> bool:
        return self.send_text(str(digest.get("one_sentence", "")))

    def send_text(self, text: str) -> bool:
        if not self.enabled or not self.token or not self.chat_id or not text.strip() or len(text) > 4096:
            return False
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
                timeout=(10, 30),
            )
            response.raise_for_status()
            return bool(response.json().get("ok"))
        except (requests.RequestException, ValueError):
            return False
