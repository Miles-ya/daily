from __future__ import annotations

import hashlib
import re

from daily.models import Document, Metric
from daily.pipeline.aggregate import period_key


METRIC_PATTERNS = {
    "industrial_production": ("规模以上工业增加值", "工业"),
    "retail_sales": ("社会消费品零售总额", "消费"),
    "fixed_asset_investment": ("固定资产投资", "投资"),
    "private_investment": ("民间投资", "民间投资"),
    "real_estate": ("房地产开发投资", "房地产"),
    "employment": ("城镇调查失业率", "就业"),
    "cpi": ("居民消费价格", "CPI"),
    "ppi": ("工业生产者出厂价格", "PPI"),
    "imports_exports": ("货物进出口总额", "外贸"),
    "service_sector": ("服务业生产指数", "服务业"),
    "energy": ("能源生产", "能源"),
}


def _nearby_percentage(content: str, phrase: str) -> tuple[float | None, str]:
    for match in re.finditer(re.escape(phrase), content):
        excerpt = content[match.start(): match.start() + 180].replace("\n", " ")
        number = re.search(r"(?:同比|比上年同期|增长|下降|为)[^。；]{0,24}?(-?\d+(?:\.\d+)?)%", excerpt)
        if number:
            value = float(number.group(1))
            if "下降" in excerpt[:number.end()] and value > 0:
                value = -value
            return value, excerpt[:160]
    return None, ""


def extract_metrics(document: Document) -> list[Metric]:
    metrics: list[Metric] = []
    period = period_key(document)
    for key, (phrase, name) in METRIC_PATTERNS.items():
        value, source_text = _nearby_percentage(document.content, phrase)
        if value is None:
            continue
        metric_id = hashlib.sha256(f"{key}:{period}:{document.id}".encode()).hexdigest()[:20]
        metrics.append(Metric(
            id=metric_id, channel=document.channel, key=key, name=name, period=period,
            value=value, unit="%", yoy=value, source_document=document.id, source_text=source_text,
        ))
    return metrics


def add_history(metrics: list[Metric], historical: list[dict]) -> list[Metric]:
    by_key: dict[str, list[dict]] = {}
    for item in historical:
        by_key.setdefault(item["key"], []).append(item)
    for metric in metrics:
        previous = sorted((m for m in by_key.get(metric.key, []) if m.get("period", "") < metric.period), key=lambda m: m["period"])
        if previous and previous[-1].get("value") is not None and metric.value is not None:
            metric.previous_value = previous[-1]["value"]
            metric.change = round(metric.value - metric.previous_value, 3)
            metric.direction = "up" if metric.change > 0 else "down" if metric.change < 0 else "flat"
    return metrics
