import json
from datetime import date
from pathlib import Path

from daily.collectors.base import DiscoveredItem
from daily.collectors.policy import GenericPolicyCollector
from daily.models import PolicyDocument
from daily.notifications.policy import _alert_message, _delivery_tier, _is_recent, _signal_message
from daily.pipeline.policy import classify_status, detect_topics, is_policy_candidate, score_policy
from daily.policy_runner import _is_retained
from daily.site.policy_builder import build_policy_site


def policy(identifier="p1"):
    return PolicyDocument(
        id=identifier, source_id="miit", source_name="工业和信息化部", url="https://example.com/policy",
        canonical_url="https://example.com/policy", title="关于支持人工智能中小企业发展的通知",
        publish_date="2026-08-20", publish_time="10:30", crawl_time="2026-08-20T10:35:00+08:00",
        content="支持人工智能中小企业发展，安排政府采购并开展试点。", content_hash="hash",
        issuing_bodies=["工业和信息化部"], document_number="工信发〔2026〕10号", topics=["产业方向", "资金流向", "创业机会"],
    )


def assessment(identifier="p1"):
    analysis = {
        "one_sentence": "政策通过政府采购支持人工智能中小企业试点。", "what_changed": ["新增人工智能中小企业试点"],
        "policy_tools": ["政府采购"], "funds_flow": {"confirmed": ["政府采购"], "unknown": []},
        "affected_industries": ["企业 AI"], "opportunities_1_3y": ["企业自动化服务"],
        "student_signals": ["积累 AI ToB 项目能力"], "city_signals": [], "macro_signals": [],
        "risks": ["试点范围尚未公布"], "deadlines": [], "evidence": ["原文明确提出政府采购"],
        "importance": "important", "importance_reason": "出现政府采购", "confidence": 0.8,
    }
    return {"policy_id": identifier, "content_hash": "hash", "relevant": True, "topics": ["产业方向", "资金流向", "创业机会"],
            "importance": "important", "score": 80, "analysis_status": "complete", "analysis": analysis, "assessed_at": "now"}


def test_policy_filter_topics_and_score():
    item = policy()
    assert is_policy_candidate(item.title)
    assert not is_policy_candidate("工业和信息化部召开工作会议")
    assert classify_status("人工智能管理办法（征求意见稿）") == "draft"
    assert detect_topics(item.title, item.content) == ["产业方向", "资金流向", "创业机会"]
    item.topics = detect_topics(item.title, item.content)
    score, reason = score_policy(item)
    assert score >= 70
    assert "资金" in reason
    assert detect_topics("关于普通行政事项的通知", "会议在北京召开，其他内容与主题无关。") == []


def personal_brief(score=1, decision="无需关注", actions=None):
    return {
        "headline": "财政贴息政策扩围", "what_happened": "财政继续降低消费和小微企业融资成本。",
        "resource_flow": "贴息流向消费者与小微企业", "market_demand": "融资需求",
        "beneficiaries": ["小微企业"], "entry_point": "目前没有直接切入点",
        "relevance_score": score, "relevance_reason": "与你当前 AI 和低成本创业方向关系较弱。",
        "decision": decision, "action_items": actions or [],
        "realert_condition": "出现面向 AI 或数字化创业的具体补贴时再提醒。", "window": "",
    }


def test_telegram_separates_national_importance_from_personal_relevance():
    item = policy().to_dict()
    brief = personal_brief()
    assert _delivery_tier(assessment(), brief) == "signal"
    message = _signal_message(item, assessment(), brief, "https://example.com/daily/")
    assert "国家重要" in message
    assert "与我低相关" in message
    assert "行动：无" in message
    assert "持续观察" not in message
    assert item["title"] not in message
    assert len(message) < 500


def test_telegram_only_strongly_alerts_actionable_high_relevance():
    item = policy().to_dict()
    brief = personal_brief(5, "立即行动", ["核对申报资格", "准备项目材料"])
    assert _delivery_tier(assessment(), brief) == "alert"
    message = _alert_message(item, brief, "https://example.com/daily/")
    assert "🚨" in message
    assert "1. 核对申报资格" in message
    assert "2. 准备项目材料" in message


def test_telegram_suppresses_irrelevant_updates():
    brief = {**personal_brief(0), "realert_condition": ""}
    assert _delivery_tier(assessment(), brief) == "silent"


def test_telegram_only_sends_recent_policies():
    today = date(2026, 8, 20)
    assert _is_recent({"publish_date": "2026-08-18"}, today)
    assert not _is_recent({"publish_date": "2026-08-16"}, today)
    assert not _is_recent({"publish_date": ""}, today)


def test_policy_retention_keeps_only_recent_90_days():
    today = date(2026, 8, 20)
    assert _is_retained("2026-08-20", today, 90)
    assert _is_retained("2026-05-22", today, 90)
    assert not _is_retained("2026-05-21", today, 90)
    assert not _is_retained("2017-11-13", today, 90)
    assert not _is_retained("", today, 90)
    assert not _is_retained("日期未知", today, 90)
    assert not _is_retained("2026-08-21", today, 90)


def test_generic_policy_collector(monkeypatch):
    listing = '<html><a href="/xxgk/zcfb/202608/t1.html">关于支持人工智能产业发展的通知</a><span>2026-08-20</span></html>'
    detail = '<html><h1>关于支持人工智能产业发展的通知</h1><div class="article">发布时间：2026年8月20日 10:30 工信发〔2026〕10号 自2026年9月1日起施行。支持人工智能产业发展。</div></html>'

    class Response:
        status_code = 200
        headers = {"content-type": "text/html"}

        def __init__(self, text, url):
            self.text = text
            self.content = text.encode()
            self.url = url

    collector = GenericPolicyCollector("miit", {"name": "工业和信息化部", "list_urls": ["https://example.com/list/"], "include_patterns": ["/xxgk/zcfb/"], "max_documents": 10})
    monkeypatch.setattr(collector, "_get", lambda url: Response(listing if url.endswith("/list/") else detail, url))
    items = collector.discover()
    assert len(items) == 1
    result = collector.collect(items[0])
    assert result.document_number == "工信发〔2026〕10号"
    assert result.effective_date == "2026-09-01"
    assert result.publish_time == "10:30"


def test_policy_site_is_feed_not_daily(tmp_path):
    root = Path(__file__).parents[1]
    output = tmp_path / "site"
    item = policy().to_dict()
    build_policy_site(root, output, "/daily/", [item], {"p1": assessment()})
    html = (output / "index.html").read_text(encoding="utf-8")
    detail = (output / "policies/p1/index.html").read_text(encoding="utf-8")
    assert "政策更新流" in html
    assert "今日暂无日报" not in html
    assert "企业自动化服务" in detail
    assert (output / "topics/industry/index.html").exists()
    public = "\n".join(path.read_text(encoding="utf-8") for path in output.rglob("*.html"))
    assert "PERSONAL_PROFILE_JSON" not in public
    assert "所以我该干什么" not in public


def test_personal_schema_is_not_public_data():
    value = json.dumps({"identity": "学生", "private_note": "深圳优先级 +1"}, ensure_ascii=False)
    assert "private_note" not in json.dumps(policy().to_dict(), ensure_ascii=False)
    assert "深圳优先级" not in json.dumps(assessment(), ensure_ascii=False)
    assert "深圳优先级" in value
