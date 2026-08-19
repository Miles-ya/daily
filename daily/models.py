from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class Document:
    id: str
    channel: str
    source_id: str
    source_name: str
    url: str
    canonical_url: str
    title: str
    publish_date: str | None
    publish_time: str | None
    crawl_time: str
    content: str
    content_hash: str
    document_type: str = "ordinary_document"
    department: str = ""
    tags: list[str] = field(default_factory=list)
    related_urls: list[str] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Document":
        return cls(**value)


@dataclass(slots=True)
class Metric:
    id: str
    channel: str
    key: str
    name: str
    period: str
    value: float | None
    unit: str
    yoy: float | None = None
    mom: float | None = None
    ytd: float | None = None
    previous_value: float | None = None
    change: float | None = None
    direction: Literal["up", "down", "flat", "unknown"] = "unknown"
    source_document: str = ""
    source_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EconomicEvent:
    id: str
    channel: str
    title: str
    date: str
    event_type: str
    primary_document: str
    documents: list[str]
    metrics: list[dict[str, Any]] = field(default_factory=list)
    official_interpretation: list[str] = field(default_factory=list)
    analysis: dict[str, Any] = field(default_factory=dict)
    score: int = 0
    score_breakdown: dict[str, int] = field(default_factory=dict)
    featured: bool = False
    recommendation_reason: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
