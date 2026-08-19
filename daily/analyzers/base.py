from __future__ import annotations

from abc import ABC, abstractmethod

from daily.models import EconomicEvent


class AnalyzerProvider(ABC):
    @abstractmethod
    def analyze(self, event: EconomicEvent, documents: list[dict]) -> dict: ...
