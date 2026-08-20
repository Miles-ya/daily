from __future__ import annotations

import hashlib
import html
import json
import os
import tempfile
from pathlib import Path

from daily.analyzers import DeepSeekAnalyzer
from daily.analyzers.policy_prompt import PERSONAL_SYSTEM_PROMPT
from daily.models import EconomicEvent
from daily.notifications.telegram import TelegramNotification
from daily.policy_runner import load_policy_data
from daily.storage import Storage


def _fallback_brief(assessment: dict) -> dict:
    analysis = assessment.get("analysis", {})
    return {
        "why_for_me": "与已选择的政策方向相关，建议先阅读公开分析。",
        "action_today": "无",
        "continue_watching": analysis.get("affected_industries", [])[:2],
        "new_directions": analysis.get("opportunities_1_3y", [])[:2],
        "suggested_judgement_changes": [],
        "ignore_reason": "私人 AI 分析暂不可用。",
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


def _line_items(values: list[str]) -> str:
    return "\n".join(f"• {html.escape(value)}" for value in values[:3]) or "• 无"


def _message(policy: dict, assessment: dict, brief: dict, site_url: str) -> str:
    analysis = assessment.get("analysis", {})
    badge = "🔴 重要" if assessment.get("importance") == "important" else "🟢 更新"
    report_url = f"{site_url.rstrip('/')}/policies/{policy['id']}/"
    return (
        f"<b>{badge}｜{html.escape(' / '.join(policy.get('topics', [])))}</b>\n"
        f"<b>{html.escape(policy['title'])}</b>\n\n"
        f"{html.escape(analysis.get('one_sentence', ''))}\n\n"
        f"<b>对我</b>\n{html.escape(brief.get('why_for_me', ''))}\n\n"
        f"<b>所以我该干什么？</b>\n{html.escape(brief.get('action_today', '无'))}\n\n"
        f"<b>持续观察</b>\n{_line_items(brief.get('continue_watching', []))}\n"
        f"<b>新出现方向</b>\n{_line_items(brief.get('new_directions', []))}\n"
        f"<b>建议判断变化</b>\n{_line_items(brief.get('suggested_judgement_changes', []))}\n\n"
        f"<a href=\"{html.escape(policy['url'])}\">官方原文</a> · <a href=\"{html.escape(report_url)}\">完整解析</a>"
    )


def _batch_item(policy: dict, brief: dict, site_url: str) -> str:
    report_url = f"{site_url.rstrip('/')}/policies/{policy['id']}/"
    topics = " / ".join(policy.get("topics", [])) or "相关政策"
    return (
        f"<b>{html.escape(topics)}｜{html.escape(policy['title'])}</b>\n"
        f"{html.escape(brief.get('why_for_me', ''))}\n"
        f"<b>行动：</b>{html.escape(brief.get('action_today', '无'))}\n"
        f"<a href=\"{html.escape(policy['url'])}\">原文</a> · "
        f"<a href=\"{html.escape(report_url)}\">解析</a>"
    )


def _chunks(items: list[tuple[tuple[str, dict, dict], str]], limit: int = 3900):
    header = "<b>本轮政策更新</b>\n\n"
    current: list[tuple[tuple[str, dict, dict], str]] = []
    size = len(header)
    for entry in items:
        added = len(entry[1]) + (4 if current else 0)
        if current and size + added > limit:
            yield header + "\n\n——\n\n".join(text for _, text in current), [meta for meta, _ in current]
            current, size = [], len(header)
        current.append(entry)
        size += added
    if current:
        yield header + "\n\n——\n\n".join(text for _, text in current), [meta for meta, _ in current]


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
    storage = Storage(root / "data")
    ledger = storage.read_json("notifications", "telegram.json", default={"sent": {}})
    candidates = []
    for policy_id in policy_ids:
        policy = policies_by_id.get(policy_id)
        assessment = assessments.get(policy_id)
        if not policy or not assessment:
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
        important = [item for item in candidates if item[2].get("importance") == "important"]
        normal = [item for item in candidates if item[2].get("importance") != "important"]
        for identity, policy, assessment in important:
            brief = _personal_brief(policy, assessment, profile, analyzer)
            if provider.send_text(_message(policy, assessment, brief, site_url)):
                ledger["sent"][identity] = {"policy_id": policy["id"], "content_hash": assessment.get("content_hash", "")}
                sent += 1
        batch_items = []
        for identity, policy, assessment in normal:
            brief = _personal_brief(policy, assessment, profile, analyzer)
            has_signal = brief.get("continue_watching") or brief.get("new_directions") or brief.get("suggested_judgement_changes") or brief.get("action_today") not in ("", "无")
            if has_signal:
                batch_items.append(((identity, policy, assessment), _batch_item(policy, brief, site_url)))
        for message, identities in _chunks(batch_items):
            if provider.send_text(message):
                for identity, policy, assessment in identities:
                    ledger["sent"][identity] = {"policy_id": policy["id"], "content_hash": assessment.get("content_hash", "")}
                    sent += 1
    storage.write_json(ledger, "notifications", "telegram.json")
    return {"enabled": True, "sent": sent, "candidates": len(candidates)}
