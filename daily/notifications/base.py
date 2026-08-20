from __future__ import annotations

from abc import ABC, abstractmethod


class NotificationProvider(ABC):
    @abstractmethod
    def send_digest(self, digest: dict) -> bool: ...

    @abstractmethod
    def send_text(self, text: str) -> bool: ...
