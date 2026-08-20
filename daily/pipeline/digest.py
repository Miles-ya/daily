from __future__ import annotations

from daily.models import Document, EconomicEvent


def build_digest(channel: str, report_date: str, documents: list[Document], document_analyses: dict[str, dict],
                 events: list[EconomicEvent], generated_on: str) -> dict:
    dated_documents = [document for document in documents if document.channel == channel and document.publish_date == report_date]
    dated_events = [event for event in events if event.channel == channel and event.date == report_date]
    event_by_document = {document_id: event for event in dated_events for document_id in event.documents}
    if not dated_documents:
        return {"channel": channel, "date": report_date, "generated_on": generated_on, "status": "empty",
                "one_sentence": "", "highlights": [], "documents": [], "sections": {}}
    items = []
    for document in dated_documents:
        wrapper = document_analyses.get(document.id, {})
        analysis = wrapper.get("analysis", {})
        event = event_by_document.get(document.id)
        items.append({"id": document.id, "title": document.title, "source_name": document.source_name,
                      "document_type": document.document_type, "url": document.url, "content_hash": document.content_hash, "analysis": analysis,
                      "attention_score": event.score if event else 0})
    items.sort(key=lambda item: (item["attention_score"], bool(item["analysis"])), reverse=True)
    complete = all(item["analysis"] for item in items)
    primary_event = next((event for event in sorted(dated_events, key=lambda event: event.score, reverse=True) if event.analysis), None)
    primary_analysis = primary_event.analysis if primary_event else next((item["analysis"] for item in items if item["analysis"]), {})
    highlights = []
    for item in items:
        analysis = item["analysis"]
        point = analysis.get("recommendation_reason") or analysis.get("overall_judgement")
        if point and point not in highlights:
            highlights.append(point)
        if len(highlights) == 3:
            break
    return {"channel": channel, "date": report_date, "generated_on": generated_on,
            "status": "published" if complete else "unavailable", "one_sentence": primary_analysis.get("one_sentence", ""),
            "highlights": highlights, "documents": items,
            "sections": {"overall_judgement": primary_analysis.get("overall_judgement", ""),
                         "strong_signals": primary_analysis.get("strong_signals", []), "weak_signals": primary_analysis.get("weak_signals", []),
                         "risks": primary_analysis.get("risks", []), "watch_next": primary_analysis.get("watch_next", [])}}
