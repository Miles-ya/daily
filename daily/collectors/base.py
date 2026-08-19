from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from daily.models import Document


@dataclass(slots=True)
class DiscoveredItem:
    url: str
    title: str = ""
    publish_date: str | None = None


class Collector(ABC):
    source_id: str
    channel: str

    @abstractmethod
    def discover(self) -> list[DiscoveredItem]: ...

    @abstractmethod
    def collect(self, item: DiscoveredItem) -> Document: ...
