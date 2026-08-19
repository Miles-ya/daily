from pathlib import Path

from daily.collectors.stats_gov import StatsGovCollector, canonicalize_url
from daily.collectors.base import DiscoveredItem
from daily.models import Document, EconomicEvent
from daily.pipeline.aggregate import aggregate_events, period_key
from daily.pipeline.classify import classify_document
from daily.pipeline.deduplicate import deduplicate
from daily.pipeline.metrics import add_history, extract_metrics
from daily.pipeline.scoring import score_event


def document(title="2026年7月份国民经济运行情况", content="规模以上工业增加值同比增长5.7%。", kind="ordinary_document"):
    return Document("doc1", "economy", "stats_gov", "国家统计局", "https://example/a", "https://example/a", title,
                    "2026-08-17", None, "2026-08-19T00:00:00+00:00", content, "hash1", kind)


def test_url_and_deduplicate():
    assert canonicalize_url("HTTPS://WWW.STATS.GOV.CN//sj/a.html?x=1#top") == "https://www.stats.gov.cn/sj/a.html"
    first = document()
    second = document()
    second.id = "doc2"
    assert len(deduplicate([first, second])) == 1


def test_classification_aggregation_and_score():
    macro = classify_document(document())
    assert macro.document_type == "macro_overview"
    assert period_key(macro) == "2026-07"
    interpretation = document("2026年7月份国民经济运行情况解读", "官方解释", "official_interpretation")
    interpretation.id, interpretation.content_hash, interpretation.url, interpretation.canonical_url = "doc2", "hash2", "https://example/b", "https://example/b"
    events = aggregate_events([macro, interpretation])
    assert len(events) == 1
    assert events[0].documents == ["doc1", "doc2"]
    assert score_event(events[0]).score >= 65


def test_metric_provenance_and_history():
    doc = document(content="规模以上工业增加值同比增长5.7%。社会消费品零售总额同比增长4.8%。")
    metrics = extract_metrics(doc)
    assert {m.key for m in metrics} == {"industrial_production", "retail_sales"}
    assert all(m.source_text and m.source_document == "doc1" for m in metrics)
    updated = add_history(metrics, [{"key": "industrial_production", "period": "2026-06", "value": 6.1}])
    industrial = next(m for m in updated if m.key == "industrial_production")
    assert industrial.previous_value == 6.1 and industrial.direction == "down"


def test_fixture_parser(monkeypatch):
    html = (Path(__file__).parent / "fixtures/stats_macro.html").read_text(encoding="utf-8")
    class Response:
        text = html
        status_code = 200
        headers = {"content-type": "text/html"}
    collector = StatsGovCollector([])
    monkeypatch.setattr(collector, "_get", lambda url: Response())
    doc = classify_document(collector.collect(DiscoveredItem("https://www.stats.gov.cn/sj/zxfb/202608/t20260817_1965056.html")))
    assert doc.publish_date == "2026-08-17"
    assert doc.publish_time is None
    assert doc.document_type == "macro_overview"
    assert len(extract_metrics(doc)) >= 5
