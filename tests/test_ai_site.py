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
            return iter([b"data: " + chunk[:150], chunk[150:], b"data: [DONE]"])
    monkeypatch.setattr("daily.analyzers.deepseek.requests.post", lambda *args, **kwargs: Response())
    analyzer = DeepSeekAnalyzer(tmp_path, api_key="test")
    event = EconomicEvent("e", "economy", "title", "2026-08-17", "macro_release", "d", ["d"])
    assert analyzer.analyze(event, [])["confidence"] == 0.6


def test_base_path_build(tmp_path):
    root = Path(__file__).parents[1]
    output = tmp_path / "site"
    doc = {"id": "d", "url": "https://example.com", "title": "原文", "publish_date": None}
    event = {"id": "e", "channel": "economy", "title": "事件", "date": "2026-08-17", "event_type": "macro_release",
             "primary_document": "d", "documents": ["d"], "metrics": [], "official_interpretation": [], "analysis": {},
             "score": 70, "featured": True, "recommendation_reason": "重要", "tags": ["宏观"]}
    digest = {"channel": "economy", "date": "2026-08-19", "one_sentence": "今日重点", "important_events": [],
              "biggest_change": "暂无", "industry_signals": [], "risks": []}
    build_site(root, output, "/daily/", [doc], [event], [digest], [])
    html = (output / "index.html").read_text(encoding="utf-8")
    assert 'href="/daily/assets/style.css"' in html
    assert 'href="/assets/' not in html
    assert (output / "events/e/index.html").exists()
    assert normalize_base_url("daily") == "/daily/"
