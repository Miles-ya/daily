from daily.models import Document
from daily.pipeline.digest import build_digest


def document(identifier="d", publish_date="2026-08-19"):
    return Document(identifier, "economy", "nbs", "国家统计局", f"https://example.com/{identifier}",
                    f"https://example.com/{identifier}", "测试资料", publish_date, None,
                    "2026-08-20T00:00:00+00:00", "正文", identifier, "ordinary_document")


def test_empty_day_never_borrows_previous_documents():
    result = build_digest("economy", "2026-08-20", [document(publish_date="2026-08-19")], {}, [], "now")
    assert result["status"] == "empty"
    assert result["documents"] == []


def test_day_waits_until_every_document_has_analysis():
    docs = [document("a"), document("b")]
    analyses = {"a": {"analysis": {"one_sentence": "一句话", "overall_judgement": "判断"}}}
    result = build_digest("economy", "2026-08-19", docs, analyses, [], "now")
    assert result["status"] == "unavailable"


def test_day_publishes_after_every_document_is_analyzed():
    docs = [document("a"), document("b")]
    analysis = {"one_sentence": "一句话", "overall_judgement": "判断", "recommendation_reason": "值得关注"}
    analyses = {item.id: {"analysis": analysis} for item in docs}
    result = build_digest("economy", "2026-08-19", docs, analyses, [], "now")
    assert result["status"] == "published"
    assert len(result["documents"]) == 2
