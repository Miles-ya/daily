from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from daily.analyzers import DeepSeekAnalyzer
from daily.collectors import StatsGovCollector
from daily.collectors.base import DiscoveredItem
from daily.config import load_config
from daily.models import Document, EconomicEvent
from daily.pipeline.aggregate import aggregate_events
from daily.pipeline.classify import classify_document
from daily.pipeline.deduplicate import deduplicate
from daily.pipeline.digest import build_digest
from daily.pipeline.metrics import add_history, extract_metrics
from daily.pipeline.scoring import score_event
from daily.site import build_site
from daily.storage import Storage

LOGGER = logging.getLogger("daily")


def _load_all_documents(storage: Storage) -> list[Document]:
    documents: list[Document] = []
    directory = storage.root / "documents"
    for path in sorted(directory.glob("*.json")) if directory.exists() else []:
        documents.append(classify_document(Document.from_dict(json.loads(path.read_text(encoding="utf-8")))))
    return documents


def run_pipeline(root: Path, run_date: str | None = None, online: bool = True, enable_ai: bool = True,
                 urls: list[str] | None = None, max_documents: int | None = None) -> dict:
    china_now = datetime.now(ZoneInfo("Asia/Shanghai"))
    report_date = run_date or (china_now.date() - timedelta(days=1)).isoformat()
    generated_on = china_now.replace(microsecond=0).isoformat()
    config = load_config(root)
    storage = Storage(root / "data")
    source = config["sources"]["stats_gov"]
    collector = StatsGovCollector(
        source["list_urls"], timeout=config["pipeline"]["request_timeout"],
        retries=config["pipeline"]["request_retries"], user_agent=config["pipeline"]["user_agent"],
        max_documents=max_documents or source["max_documents"],
    )
    new_documents: list[Document] = []
    errors: list[dict] = []
    if online:
        try:
            items = collector.discover() if not urls else [DiscoveredItem(url=url) for url in urls]
        except Exception as exc:
            items = []
            errors.append({"stage": "discover", "source": "stats_gov", "error": str(exc)})
        for item in items:
            try:
                document = classify_document(collector.collect(item))
                new_documents.append(document)
                storage.write_json(document.to_dict(), "raw", report_date, f"{document.id}.json")
            except Exception as exc:
                errors.append({"stage": "collect", "url": item.url, "error": str(exc)})
                LOGGER.warning("collect failed for %s: %s", item.url, exc)
    # Freshly fetched copies win for the same canonical URL, allowing corrected
    # parsing and upstream content revisions while retaining stable IDs.
    all_documents = deduplicate(new_documents + _load_all_documents(storage))
    for document in all_documents:
        storage.write_json(document.to_dict(), "documents", f"{document.id}.json")

    historical = storage.read_json("metrics", "series.json", default=[])
    fresh_metrics = []
    for document in all_documents:
        fresh_metrics.extend(extract_metrics(document))
    fresh_metrics = add_history(fresh_metrics, historical)
    metrics_dicts = [metric.to_dict() for metric in fresh_metrics]
    document_types = {document.id: document.document_type for document in all_documents}
    unique_metrics: dict[tuple[str, str], dict] = {}
    for metric in [*historical, *metrics_dicts]:
        identity = (metric["key"], metric["period"])
        existing = unique_metrics.get(identity)
        if existing is None or document_types.get(metric["source_document"]) == "macro_overview":
            unique_metrics[identity] = metric
    all_metrics = sorted(unique_metrics.values(), key=lambda m: (m["period"], m["key"], m["source_document"]))

    existing_events = {
        value["id"]: value
        for path in (root / "data/events").glob("*.json")
        if (value := json.loads(path.read_text(encoding="utf-8")))
    }
    events = aggregate_events(all_documents)
    event_by_document = {document_id: event for event in events for document_id in event.documents}
    # Event details keep the metric extracted from that event's own documents,
    # while the global time series above has one authoritative value per period.
    for metric in metrics_dicts:
        event = event_by_document.get(metric["source_document"])
        if event:
            metric["event_id"] = event.id
            if not any((existing.get("key"), existing.get("period")) == (metric["key"], metric["period"]) for existing in event.metrics):
                event.metrics.append(metric)
    for metric in all_metrics:
        event = event_by_document.get(metric["source_document"])
        metric["event_id"] = event.id if event else ""
    analyzer = DeepSeekAnalyzer(root / "data/ai_cache")
    usage: list[dict] = []
    docs_dict = {document.id: document.to_dict() for document in all_documents}
    existing_document_analyses = {
        value["document_id"]: value
        for path in (root / "data/document_analyses").glob("*.json")
        if (value := json.loads(path.read_text(encoding="utf-8")))
    }
    document_analyses: dict[str, dict] = {}
    for document in all_documents:
        previous = existing_document_analyses.get(document.id, {})
        analysis = previous.get("analysis", {}) if previous.get("content_hash") == document.content_hash else {}
        synthetic_event = EconomicEvent(id=f"document-analysis-{document.id}", channel=document.channel, title=document.title,
                                        date=document.publish_date or "", event_type=document.document_type,
                                        primary_document=document.id, documents=[document.id])
        try:
            if enable_ai:
                updated = analyzer.analyze(synthetic_event, [document.to_dict()])
                if updated:
                    analysis = updated
                if analyzer.last_usage:
                    usage.append({"document_id": document.id, "kind": "document", **analyzer.last_usage})
        except Exception as exc:
            errors.append({"stage": "analyze_document", "document": document.id, "error": str(exc)})
        wrapper = {"document_id": document.id, "channel": document.channel, "publish_date": document.publish_date,
                   "content_hash": document.content_hash, "analysis": analysis}
        document_analyses[document.id] = wrapper
        storage.write_json(wrapper, "document_analyses", f"{document.id}.json")
    for event in events:
        previous_event = existing_events.get(event.id, {})
        event.analysis = previous_event.get("analysis", {})
        event_documents = [docs_dict[doc_id] for doc_id in event.documents]
        if enable_ai and analyzer.enabled and event.analysis and previous_event.get("documents") == event.documents:
            analyzer.prime_cache(event, event_documents, event.analysis)
        try:
            if enable_ai:
                updated_analysis = analyzer.analyze(event, event_documents)
                if updated_analysis:
                    event.analysis = updated_analysis
                if analyzer.last_usage:
                    usage.append({"event_id": event.id, **analyzer.last_usage})
        except Exception as exc:
            errors.append({"stage": "analyze", "event": event.id, "error": str(exc)})
        score_event(event)
        if event.analysis.get("recommendation_reason"):
            event.recommendation_reason = event.analysis["recommendation_reason"]

    event_dicts = [event.to_dict() for event in events]
    storage.write_json(all_metrics, "metrics", "series.json")
    digest_dates = {document.publish_date for document in all_documents if document.publish_date}
    digest_dates.add(report_date)
    for digest_date in sorted(digest_dates):
        existing_digest = storage.read_json("daily", f"{digest_date}.json", default=None)
        current_signature = sorted((document.id, document.content_hash) for document in all_documents
                                   if document.channel == "economy" and document.publish_date == digest_date)
        existing_signature = sorted((item.get("id", ""), item.get("content_hash", ""))
                                    for item in (existing_digest or {}).get("documents", []))
        unchanged = existing_digest and existing_digest.get("status") in {"published", "empty"} and current_signature == existing_signature
        if unchanged and digest_date != report_date:
            continue
        digest = build_digest("economy", digest_date, all_documents, document_analyses, events, generated_on)
        storage.write_json(digest, "daily", f"{digest_date}.json")
    for event in events:
        storage.write_json(event.to_dict(), "events", f"{event.id}.json")
    storage.write_json({"date": report_date, "generated_on": generated_on, "errors": errors, "ai_calls": usage}, "logs", f"{report_date}.json")
    digests = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((root / "data/daily").glob("*.json"))]
    build_site(root, root / "site-output", config["site"]["base_url"], [d.to_dict() for d in all_documents], event_dicts, digests, all_metrics,
               document_analyses=document_analyses, report_date=report_date)
    return {"date": report_date, "documents": len(all_documents), "document_analyses": sum(bool(value.get("analysis")) for value in document_analyses.values()),
            "new_documents": len(new_documents), "events": len(events),
            "metrics": len(all_metrics), "featured": sum(event.featured for event in events), "ai_enabled": analyzer.enabled and enable_ai,
            "errors": errors, "site": str(root / "site-output")}
