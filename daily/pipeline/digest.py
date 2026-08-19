from __future__ import annotations

from daily.models import EconomicEvent


def build_digest(channel: str, run_date: str, events: list[EconomicEvent]) -> dict:
    important = [event for event in events if event.featured and event.date == run_date][:5]
    if not important:
        important = [event for event in events if event.featured][:5]
    if not important:
        return {"channel": channel, "date": run_date, "one_sentence": "今日暂无重大经济数据或政策更新。",
                "important_events": [], "temperature": None, "biggest_change": "数据不足，目前无法判断。",
                "money_flow": {"confirmed": [], "inferred": []}, "industry_signals": [], "risks": [], "watch_next": []}
    primary = important[0]
    analyses = [event.analysis for event in important if event.analysis]
    return {
        "channel": channel, "date": run_date,
        "one_sentence": (analyses[0].get("one_sentence") if analyses else f"今日重点关注：{primary.title}。"),
        "important_events": [{"id": e.id, "title": e.title, "score": e.score, "summary": e.analysis.get("one_sentence", "")} for e in important],
        "temperature": analyses[0].get("economic_temperature") if analyses else None,
        "biggest_change": (analyses[0].get("overall_judgement") if analyses else "等待更多历史数据形成稳定比较。"),
        "money_flow": analyses[0].get("money_flow", {"confirmed": [], "inferred": []}) if analyses else {"confirmed": [], "inferred": []},
        "industry_signals": analyses[0].get("industry_signals", []) if analyses else [],
        "risks": analyses[0].get("risks", []) if analyses else [],
        "watch_next": analyses[0].get("watch_next", []) if analyses else [],
    }
