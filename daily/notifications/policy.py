from __future__ import annotations

import hashlib
import html
import json
import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from daily.analyzers import DeepSeekAnalyzer
from daily.analyzers.policy_prompt import PERSONAL_SYSTEM_PROMPT
from daily.models import EconomicEvent
from daily.notifications.telegram import TelegramNotification
from daily.policy_runner import load_policy_data
from daily.storage import Storage


def _fallback_brief(assessment: dict) -> dict:
    analysis = assessment.get("analysis", {})
    return {
        "headline": "政策更新", "what_happened": analysis.get("one_sentence", "")[:80],
        "resource_flow": "未判断", "market_demand": "未判断", "beneficiaries": [],
        "entry_point": "未发现", "relevance_score": 0,
        "relevance_reason": "私人 AI 分析暂不可用。", "decision": "无需关注",
        "action_items": [], "realert_condition": "", "window": "",
    }


def _personal_brief(policy: dict, assessment: dict, profile: dict, analyzer: DeepSeekAnalyzer) -> dict:
    source = {"policy": {key: policy.get(key) for key in ("id", "title", "source_name", "publish_date", "effective_date", "topics")},
              "public_analysis": assessment.get("analysis", {}), "personal_profile": profile}
    rendered = json.dumps(source, ensure_ascii=False, sort_keys=True)
    wrapper = {"id": policy["id"], "content_hash": hashlib.sha256(rendered.encode()).hexdigest(), "content": rendered}
    event = EconomicEvent(
        id=f"personal-{policy['id']}", channel="private", title=policy["title"], date=policy.get("publish_date") or "",
        event_type="personal_policy_brief", primary_document=policy["id"], documents=[policy["id"]],
    )
    try:
        return analyzer.analyze(event, [wrapper]) or _fallback_brief(assessment)
    except Exception:
        return _fallback_brief(assessment)


def _stars(score: int) -> str:
    value = min(max(int(score), 0), 5)
    return "★" * value + "☆" * (5 - value)


def _delivery_tier(assessment: dict, brief: dict) -> str:
    score = int(brief.get("relevance_score", 0))
    actionable = bool(brief.get("action_items")) and brief.get("decision") in ("立即行动", "值得研究")
    if score >= 4 and actionable:
        return "alert"
    if score >= 2:
        return "signal"
    if assessment.get("importance") == "important" and score == 1 and brief.get("realert_condition"):
        return "signal"
    return "silent"


def _links(policy: dict, site_url: str) -> str:
    report_url = f"{site_url.rstrip('/')}/policies/{policy['id']}/"
    return (
        f'<a href="{html.escape(policy["url"])}">原文</a> · '
        f'<a href="{html.escape(report_url)}">完整解析</a>'
    )


def _signal_message(policy: dict, assessment: dict, brief: dict, site_url: str) -> str:
    national = "🔴 国家重要" if assessment.get("importance") == "important" else "⚪ 国家一般"
    score = int(brief.get("relevance_score", 0))
    relevance = "与我低相关" if score <= 1 else "与我相关"
    action = "无" if not brief.get("action_items") else brief.get("decision", "值得研究")
    trigger = brief.get("realert_condition", "")
    trigger_line = f"\n{html.escape(trigger)}" if trigger else ""
    return (
        f"<b>{national}｜⚪ {relevance}</b>\n"
        f"<b>{html.escape(brief.get('headline', '政策更新'))}</b>\n\n"
        f"{html.escape(brief.get('what_happened', ''))}\n\n"
        f"<b>与你相关度：{_stars(score)}</b>\n"
        f"<b>行动：{html.escape(action)}</b>{trigger_line}\n\n"
        f"{_links(policy, site_url)}"
    )


def _alert_message(policy: dict, brief: dict, site_url: str) -> str:
    actions = "\n".join(
        f"{index}. {html.escape(value)}" for index, value in enumerate(brief.get("action_items", [])[:3], 1)
    )
    window = brief.get("window") or "原文未说明明确截止时间"
    return (
        "🚨 <b>与你高度相关｜建议行动</b>\n"
        f"<b>{html.escape(brief.get('headline', '政策机会'))}</b>\n\n"
        f"{html.escape(brief.get('what_happened', ''))}\n\n"
        f"<b>为什么和你有关</b>\n{html.escape(brief.get('relevance_reason', ''))}\n\n"
        f"<b>你现在可以做</b>\n{actions}\n\n"
        f"<b>窗口期</b>\n{html.escape(window)}\n\n"
        f"{_links(policy, site_url)}"
    )


def _is_recent(policy: dict, today: date, max_age_days: int = 3) -> bool:
    try:
        published = date.fromisoformat(policy.get("publish_date") or "")
    except ValueError:
        return False
    return today - timedelta(days=max_age_days) <= published <= today


def notify_policies(root: Path, policy_ids: list[str], site_url: str) -> dict:
    provider = TelegramNotification()
    if not provider.enabled:
        return {"enabled": False, "sent": 0}
    try:
        profile = json.loads(os.environ.get("PERSONAL_PROFILE_JSON", "{}"))
    except json.JSONDecodeError:
        profile = {}
    policies, assessments = load_policy_data(root)
    policies_by_id = {item["id"]: item for item in policies}
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    storage = Storage(root / "data")
    ledger = storage.read_json("notifications", "telegram.json", default={"sent": {}})
    candidates = []
    for policy_id in policy_ids:
        policy = policies_by_id.get(policy_id)
        assessment = assessments.get(policy_id)
        if not policy or not assessment:
            continue
        if not _is_recent(policy, today):
            continue
        identity = f"{policy_id}:{assessment.get('content_hash', '')}"
        if identity not in ledger["sent"]:
            candidates.append((identity, policy, assessment))
    sent = 0
    with tempfile.TemporaryDirectory(prefix="policy-radar-private-") as cache:
        analyzer = DeepSeekAnalyzer(
            Path(cache), schema_path=root / "daily/schemas/personal-brief-v1.json",
            system_prompt=PERSONAL_SYSTEM_PROMPT,
        )
        suppressed = 0
        for identity, policy, assessment in candidates:
            brief = _personal_brief(policy, assessment, profile, analyzer)
            tier = _delivery_tier(assessment, brief)
            ledger_entry = {"policy_id": policy["id"], "content_hash": assessment.get("content_hash", "")}
            if tier == "silent":
                ledger["sent"][identity] = {**ledger_entry, "status": "suppressed"}
                suppressed += 1
                continue
            message = _alert_message(policy, brief, site_url) if tier == "alert" else _signal_message(policy, assessment, brief, site_url)
            if provider.send_text(message):
                ledger["sent"][identity] = {**ledger_entry, "status": tier}
                sent += 1
    storage.write_json(ledger, "notifications", "telegram.json")
    return {"enabled": True, "sent": sent, "suppressed": suppressed, "candidates": len(candidates)}
