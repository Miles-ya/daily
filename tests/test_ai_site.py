import json
from pathlib import Path

import pytest

from daily.analyzers.deepseek import DeepSeekAnalyzer
from daily.models import EconomicEvent
from daily.site.builder import build_site, normalize_base_url


def test_ai_without_key_is_graceful(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    analyzer = DeepSeekAnalyzer(tmp_path)
    event = EconomicEvent("e", "economy", "title", "2026-08-17", "macro_release", "d", ["d"])
    assert not analyzer.enabled
    assert analyzer.analyze(event, []) == {}


def test_schema_rejects_invalid(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    analyzer = DeepSeekAnalyzer(tmp_path)
    import jsonschema
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"one_sentence": "x"}, analyzer.schema)


def test_fragmented_stream_is_reassembled(tmp_path, monkeypatch):
    analysis = {
        "one_sentence": "工业增速回落。", "overall_judgement": "单月数据不足以判断长期趋势。",
        "economic_temperature": 50, "key_metrics": [], "strong_signals": [], "weak_signals": [],
        "turning_points": [], "divergences": [], "money_flow": {"confirmed": [], "inferred": []},
        "industry_signals": [], "risks": [], "watch_next": [], "recommendation_reason": "关注月度变化。",
        "confidence": 0.6,
    }
    chunk = json.dumps({"choices": [{"delta": {"content": json.dumps(analysis, ensure_ascii=False)}, "finish_reason": "stop"}], "usage": {}}, ensure_ascii=False).encode()
    class Response:
        def raise_for_status(self): pass
        def iter_lines(self, decode_unicode=False):
            usage_only = json.dumps({"choices": [], "usage": {"total_tokens": 12}}).encode()
            return iter([b"data: " + chunk[:150], chunk[150:], b"data: " + usage_only, b"data: [DONE]"])
    monkeypatch.setattr("daily.analyzers.deepseek.requests.post", lambda *args, **kwargs: Response())
    analyzer = DeepSeekAnalyzer(tmp_path, api_key="test")
    event = EconomicEvent("e", "economy", "title", "2026-08-17", "macro_release", "d", ["d"])
    assert analyzer.analyze(event, [])["confidence"] == 0.6


def test_base_path_build(tmp_path):
    root = Path(__file__).parents[1]
    output = tmp_path / "site"
    doc = {"id": "d", "channel": "economy", "url": "https://example.com", "title": "原文", "publish_date": "2026-08-19",
           "source_name": "国家统计局", "document_type": "macro_overview", "tags": [], "content_hash": "hash"}
    event = {"id": "e", "channel": "economy", "title": "事件", "date": "2026-08-17", "event_type": "macro_release",
             "primary_document": "d", "documents": ["d"], "metrics": [], "official_interpretation": [], "analysis": {},
             "score": 70, "featured": True, "recommendation_reason": "重要", "tags": ["宏观"]}
    analysis = {"one_sentence": "工业生产保持增长。", "overall_judgement": "当前数据表现平稳。",
                "strong_signals": ["生产延续增长"], "weak_signals": [], "risks": [], "watch_next": [],
                "recommendation_reason": "关注生产变化"}
    digest = {"channel": "economy", "date": "2026-08-19", "generated_on": "2026-08-20T07:15:00+08:00",
              "status": "published", "one_sentence": "工业生产保持增长。", "highlights": ["关注生产变化"],
              "documents": [{**doc, "analysis": analysis, "attention_score": 70}],
              "sections": {"overall_judgement": "当前数据表现平稳。", "strong_signals": [], "weak_signals": [], "risks": [], "watch_next": []}}
    document_analyses = {"d": {"document_id": "d", "content_hash": "hash", "analysis": analysis}}
    build_site(root, output, "/daily/", [doc], [event], [digest], [], document_analyses=document_analyses, report_date="2026-08-19")
    html = (output / "index.html").read_text(encoding="utf-8")
    assert 'href="/daily/assets/style.css"' in html
    assert 'href="/assets/' not in html
    assert (output / "events/e/index.html").exists()
    assert (output / "archive/index.html").exists()
    assert "工业生产保持增长" in html
    assert "1 份文件 · 全部完成解析" in html
    assert "宏观运行概览" in html
    assert "首页" not in html
    assert (output / "economy/2026-08-19/index.html").exists()
    assert (output / "economy/documents/d/index.html").exists()
    assert (output / "ai/index.html").exists()
    assert "今日暂无日报" in (output / "ai/index.html").read_text(encoding="utf-8")
    assert normalize_base_url("daily") == "/daily/"
