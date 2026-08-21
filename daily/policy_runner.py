from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from daily.analyzers import DeepSeekAnalyzer
from daily.analyzers.policy_prompt import POLICY_SYSTEM_PROMPT
from daily.collectors import GenericPolicyCollector
from daily.config import load_config
from daily.models import EconomicEvent, PolicyAssessment, PolicyDocument
from daily.pipeline.policy import detect_topics, score_policy
from daily.site.policy_builder import build_policy_site
from daily.storage import Storage


LOGGER = logging.getLogger("policy-radar")
DATE_IN_PATH_RE = re.compile(r"/t(20\d{2})(\d{2})(\d{2})_")


def _load_records(directory: Path, factory) -> list:
    if not directory.exists():
        return []
    return [factory(json.loads(path.read_text(encoding="utf-8"))) for path in sorted(directory.glob("*.json"))]


def _retention_cutoff(today: date, retention_days: int) -> date:
    return today - timedelta(days=max(1, retention_days))


def _is_retained(publish_date: str | None, today: date, retention_days: int) -> bool:
    if not publish_date:
        return False
    try:
        published = date.fromisoformat(publish_date)
    except ValueError:
        return False
    return _retention_cutoff(today, retention_days) <= published <= today


def _fallback_analysis(policy: PolicyDocument, importance: str, reason: str) -> dict:
    status = "征求意见" if policy.policy_status == "draft" else "正式发布"
    return {
        "one_sentence": f"{policy.source_name}{status}《{policy.title}》，完整影响仍需结合原文判断。",
        "what_changed": [f"{status}：{policy.title}"], "policy_tools": [],
        "funds_flow": {"confirmed": [], "unknown": ["未启用 AI 分析，尚未核验具体资金安排。"]},
        "affected_industries": [], "opportunities_1_3y": [], "student_signals": [],
        "city_signals": [], "macro_signals": [], "risks": ["当前仅完成规则识别，不能替代完整政策解析。"],
        "deadlines": [policy.effective_date] if policy.effective_date else [], "evidence": [policy.title],
        "importance": importance, "importance_reason": reason, "confidence": 0.35,
    }


def _deduplicate(policies: list[PolicyDocument]) -> list[PolicyDocument]:
    by_identity: dict[str, PolicyDocument] = {}
    for policy in sorted(policies, key=lambda item: (item.publish_date or "", item.crawl_time)):
        normalized_title = re.sub(r"\s+|[《》]", "", policy.title)
        identity = policy.document_number or normalized_title
        existing = by_identity.get(identity)
        if existing is None:
            by_identity[identity] = policy
            continue
        existing.issuing_bodies = sorted(set(existing.issuing_bodies + policy.issuing_bodies))
        mirrors = existing.raw_metadata.setdefault("mirror_urls", [])
        mirrors.extend(url for url in (policy.canonical_url,) if url != existing.canonical_url and url not in mirrors)
        if policy.source_id == "gov_cn" or policy.crawl_time >= existing.crawl_time:
            policy.issuing_bodies = existing.issuing_bodies
            policy.raw_metadata["mirror_urls"] = mirrors + [existing.canonical_url]
            by_identity[identity] = policy
    return list(by_identity.values())


def _repair_url_dates(policies: list[PolicyDocument]) -> None:
    for policy in policies:
        match = DATE_IN_PATH_RE.search(policy.canonical_url)
        if not match:
            continue
        value = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        if not policy.publish_date or value > policy.publish_date:
            policy.publish_date = value


def _prune_orphan_records(root: Path, policy_ids: set[str]) -> None:
    for relative in ("data/policies", "data/policy_assessments"):
        directory = root / relative
        if not directory.exists():
            continue
        for path in directory.glob("*.json"):
            if path.stem not in policy_ids:
                path.unlink()


def _analysis_event(policy: PolicyDocument) -> EconomicEvent:
    return EconomicEvent(
        id=f"policy-{policy.id}", channel="policy", title=policy.title,
        date=policy.publish_date or "", event_type="policy", primary_document=policy.id,
        documents=[policy.id], tags=policy.topics,
    )


def _prune_ai_cache(analyzer: DeepSeekAnalyzer, policies: list[PolicyDocument]) -> int:
    keep = {
        analyzer._cache_path(_analysis_event(policy), [policy.to_dict()]).name
        for policy in policies
    }
    removed = 0
    for path in analyzer.cache_dir.glob("*.json"):
        if path.name not in keep:
            path.unlink()
            removed += 1
    return removed


def load_policy_data(root: Path) -> tuple[list[dict], dict[str, dict]]:
    policies = [item.to_dict() for item in _load_records(root / "data/policies", PolicyDocument.from_dict)]
    assessments = {}
    directory = root / "data/policy_assessments"
    if directory.exists():
        for path in directory.glob("*.json"):
            value = json.loads(path.read_text(encoding="utf-8"))
            assessments[value["policy_id"]] = value
    return policies, assessments


def build_policy_output(root: Path) -> dict:
    config = load_config(root)
    policies, assessments = load_policy_data(root)
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    retention_days = config["policy"].get("retention_days", 90)
    policies = [item for item in policies if _is_retained(item.get("publish_date"), today, retention_days)]
    retained_ids = {item["id"] for item in policies}
    assessments = {key: value for key, value in assessments.items() if key in retained_ids}
    build_policy_site(root, root / "site-output", config["site"]["base_url"], policies, assessments)
    return {"site": str(root / "site-output"), "policies": len(policies)}


def run_policy_pipeline(root: Path, online: bool = True, enable_ai: bool = True) -> dict:
    now = datetime.now(ZoneInfo("Asia/Shanghai")).replace(microsecond=0)
    config = load_config(root)
    storage = Storage(root / "data")
    retention_days = config["policy"].get("retention_days", 90)
    existing_records = _load_records(root / "data/policies", PolicyDocument.from_dict)
    existing = [item for item in existing_records if _is_retained(item.publish_date, now.date(), retention_days)]
    old_signatures = {item.id: (item.content_hash, item.publish_date, item.policy_status, tuple(item.topics)) for item in existing}
    existing_by_url = {item.canonical_url: item for item in existing}
    fetched: list[PolicyDocument] = []
    errors: list[dict] = []
    discovered_count = 0
    if online:
        for source_id, source in config["sources"].items():
            if source.get("kind") != "policy" or source.get("enabled") is False:
                continue
            collector = GenericPolicyCollector(
                source_id, source, timeout=config["pipeline"]["request_timeout"],
                retries=config["pipeline"]["request_retries"], user_agent=config["pipeline"]["user_agent"],
            )
            try:
                items = collector.discover()
                items = [
                    item for item in items
                    if not item.publish_date or _is_retained(item.publish_date, now.date(), retention_days)
                ]
                discovered_count += len(items)
            except Exception as exc:
                errors.append({"stage": "discover", "source": source_id, "error": str(exc)})
                continue
            if not existing:
                items = items[:config["policy"].get("initial_backfill_per_source", 5)]
            refresh_latest = config["policy"].get("refresh_latest", 3)
            for index, item in enumerate(items):
                canonical = item.url.split("?", 1)[0].split("#", 1)[0]
                if canonical in existing_by_url and index >= refresh_latest:
                    continue
                try:
                    policy = collector.collect(item)
                    policy.topics = detect_topics(policy.title, policy.content)
                    if policy.topics and _is_retained(policy.publish_date, now.date(), retention_days):
                        fetched.append(policy)
                except Exception as exc:
                    errors.append({"stage": "collect", "source": source_id, "url": item.url, "error": str(exc)})
    policies = _deduplicate(existing + fetched)
    _repair_url_dates(policies)
    policies = [item for item in policies if _is_retained(item.publish_date, now.date(), retention_days)]
    policies.sort(key=lambda item: (item.publish_date or "", item.crawl_time), reverse=True)
    for policy in policies:
        policy.topics = detect_topics(policy.title, policy.content)
    changed = [item for item in policies if old_signatures.get(item.id) != (item.content_hash, item.publish_date, item.policy_status, tuple(item.topics))]
    existing_assessments: dict[str, dict] = {}
    directory = root / "data/policy_assessments"
    if directory.exists():
        for path in directory.glob("*.json"):
            value = json.loads(path.read_text(encoding="utf-8"))
            existing_assessments[value["policy_id"]] = value
    analyzer = DeepSeekAnalyzer(
        root / "data/policy_ai_cache",
        schema_path=root / "daily/schemas/policy-analysis-v1.json",
        system_prompt=POLICY_SYSTEM_PROMPT,
    )
    cache_pruned = _prune_ai_cache(analyzer, policies)
    retained_ids = {item.id for item in policies}
    assessments: dict[str, dict] = {
        key: value for key, value in existing_assessments.items() if key in retained_ids
    }
    analysis_budget = config["policy"].get("max_ai_per_run", 12)
    analysis_calls = 0
    assessment_updates: list[str] = []
    for policy in policies:
        previous = existing_assessments.get(policy.id)
        score, reason = score_policy(policy)
        importance = "important" if score >= config["policy"].get("important_score", 70) else "normal"
        if previous and previous.get("content_hash") == policy.content_hash:
            if previous.get("topics") != policy.topics or previous.get("score") != score:
                previous = {**previous, "topics": policy.topics, "score": score}
                if previous.get("analysis_status") != "complete":
                    previous["importance"] = importance
                    previous["analysis"] = _fallback_analysis(policy, importance, reason)
                assessments[policy.id] = previous
                assessment_updates.append(policy.id)
            if previous.get("analysis_status") == "complete" or not (enable_ai and analyzer.enabled):
                continue
            if analysis_calls >= analysis_budget:
                continue
        analysis = {}
        did_analyze = False
        try:
            if enable_ai and analyzer.enabled and analysis_calls < analysis_budget:
                event = _analysis_event(policy)
                analysis = analyzer.analyze(event, [policy.to_dict()])
                analysis_calls += 1
                did_analyze = bool(analysis)
        except Exception as exc:
            errors.append({"stage": "analyze", "policy": policy.id, "error": str(exc)})
        if not analysis:
            analysis = _fallback_analysis(policy, importance, reason)
        importance = analysis.get("importance", importance)
        assessment = PolicyAssessment(
            policy_id=policy.id, content_hash=policy.content_hash, relevant=True, topics=policy.topics,
            importance=importance, score=score, analysis_status="complete" if did_analyze else "pending",
            analysis=analysis,
        ).to_dict()
        assessments[policy.id] = assessment
        if not previous or previous.get("analysis_status") != assessment["analysis_status"] or previous.get("content_hash") != assessment["content_hash"]:
            assessment_updates.append(policy.id)
    for policy in policies:
        storage.write_json(policy.to_dict(), "policies", f"{policy.id}.json")
    for assessment in assessments.values():
        storage.write_json(assessment, "policy_assessments", f"{assessment['policy_id']}.json")
    _prune_orphan_records(root, retained_ids)
    storage.write_json(
        {
            "generated_on": now.isoformat(), "discovered": discovered_count,
            "changed": [item.id for item in changed], "retention_days": retention_days,
            "pruned": len(existing_records) - len(existing), "cache_pruned": cache_pruned,
            "errors": errors,
        },
        "policy_logs", f"{now.date().isoformat()}-{now.strftime('%H%M')}.json",
    )
    build_policy_site(
        root, root / "site-output", config["site"]["base_url"],
        [item.to_dict() for item in policies], assessments, generated_on=now.isoformat(),
    )
    return {
        "generated_on": now.isoformat(), "changed": bool(changed or assessment_updates),
        "policy_ids": sorted(item.id for item in changed),
        "analysis_updated_ids": sorted(set(assessment_updates)),
        "policies": len(policies), "discovered": discovered_count, "errors": errors,
        "ai_enabled": analyzer.enabled and enable_ai, "site": str(root / "site-output"),
    }
