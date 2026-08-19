from __future__ import annotations

import re
from collections import defaultdict
from datetime import date

from daily.models import Document, EconomicEvent


MONTH_RE = re.compile(r"(?:(\d{4})年)?(?:(\d{1,2})月份|1[—-](\d{1,2})月份)")


def period_key(document: Document) -> str:
    match = MONTH_RE.search(document.title)
    year = (match.group(1) if match else None) or (document.publish_date or str(date.today()))[:4]
    if match:
        month = match.group(2) or match.group(3)
        return f"{year}-{int(month):02d}"
    if "一季度" in document.title:
        return f"{year}-Q1"
    if "上半年" in document.title:
        return f"{year}-H1"
    if "前三季度" in document.title:
        return f"{year}-Q3"
    if "全年" in document.title:
        return f"{year}-FY"
    return document.publish_date or "undated"


def aggregate_events(documents: list[Document]) -> list[EconomicEvent]:
    groups: dict[str, list[Document]] = defaultdict(list)
    for document in documents:
        period = period_key(document)
        can_group = document.document_type in {"macro_overview", "official_interpretation", "press_conference"} and period != (document.publish_date or "undated")
        key = period if can_group else document.id
        groups[key].append(document)
    events: list[EconomicEvent] = []
    for key, group in groups.items():
        primary = next((d for d in group if d.document_type == "macro_overview"), group[0])
        is_macro = any(d.document_type == "macro_overview" for d in group)
        title = f"{key[:4]}年{int(key[5:])}月中国经济运行数据" if is_macro and re.fullmatch(r"\d{4}-\d{2}", key) else primary.title
        official = [d.content[:500] for d in group if d.document_type in {"official_interpretation", "press_conference"}]
        events.append(EconomicEvent(
            id=f"china-economy-{key}" if is_macro else f"document-{primary.id}",
            channel="economy", title=title, date=primary.publish_date or "",
            event_type="macro_release" if is_macro else primary.document_type,
            primary_document=primary.id, documents=[d.id for d in group],
            official_interpretation=official, tags=sorted({tag for d in group for tag in d.tags}),
        ))
    return sorted(events, key=lambda e: (e.date, e.id), reverse=True)
