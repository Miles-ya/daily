from daily.models import EconomicEvent


def score_event(event: EconomicEvent) -> EconomicEvent:
    macro = 25 if event.event_type == "macro_release" else 12
    scale = min(20, (16 if event.event_type == "macro_release" else 6) + len(event.metrics) * 2)
    trend = min(20, (5 if event.event_type == "macro_release" else 0) + sum(3 for m in event.metrics if m.get("change") not in (None, 0)))
    importance = 15 if event.event_type in {"macro_release", "economic_policy"} else 7
    money = min(10, sum(2 for m in event.metrics if m.get("key") in {"fixed_asset_investment", "private_investment", "real_estate"}))
    industry = min(10, len(event.tags) * 2)
    event.score_breakdown = {"macro_impact": macro, "economic_scale": scale, "trend_change": trend,
                             "data_policy_importance": importance, "capital_impact": money, "industry_impact": industry}
    event.score = min(100, sum(event.score_breakdown.values()))
    event.featured = event.score >= 65
    event.recommendation_reason = (
        "这是理解当前中国经济变化的核心官方数据，并包含可追溯的历史比较。"
        if event.event_type == "macro_release" else "该信息对观察当前经济运行具有参考价值。"
    )
    return event
