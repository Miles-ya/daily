from __future__ import annotations

import re

from daily.models import Document


MACRO_RE = re.compile(r"(?:\d+月份|1\s*[—-]\s*\d+\s*月份|一季度|上半年|前三季度|全年).*国民经济")


def classify_document(document: Document) -> Document:
    title = document.title
    if "解读" in title or "答记者问" in title or "新闻发言人就" in title:
        document.document_type = "official_interpretation"
        document.tags.append("官方解读")
    elif MACRO_RE.search(title):
        document.document_type = "macro_overview"
        document.tags.extend(["宏观", "经济运行"])
    elif "新闻发布会" in title or "发布会" in title:
        document.document_type = "press_conference"
        document.tags.append("发布会")
    elif any(word in title for word in ("增加值", "投资", "零售", "价格", "就业", "利润", "PMI", "房地产市场", "能源生产")):
        document.document_type = "economic_data"
        document.tags.append("经济数据")
    elif any(word in title for word in ("意见", "通知", "办法", "政策")):
        document.document_type = "economic_policy"
        document.tags.append("政策")
    document.tags = sorted(set(document.tags))
    return document
