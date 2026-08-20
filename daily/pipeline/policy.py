from __future__ import annotations

import re

from daily.models import PolicyDocument


TOPIC_KEYWORDS = {
    "产业方向": ("人工智能", "AI", "机器人", "低空经济", "数字经济", "Web3", "区块链", "算力", "芯片", "集成电路", "新能源", "先进制造", "工业互联网"),
    "资金流向": ("财政", "专项债", "政府采购", "产业基金", "补贴", "贴息", "奖励资金", "中央预算", "信贷", "税收优惠", "资金管理"),
    "创业机会": ("中小企业", "民营企业", "创业", "创新创业", "专精特新", "试点", "揭榜挂帅", "服务业", "营商环境"),
    "就业与城市": ("就业", "人才", "高校毕业生", "职业教育", "北京", "上海", "深圳", "杭州", "粤港澳", "长三角", "京津冀"),
    "宏观环境": ("消费", "房地产", "住房", "民间投资", "外贸", "出口", "进口", "跨境", "货币政策", "利率", "汇率", "经济增长"),
}
STRONG_TOPIC_KEYWORDS = {
    "产业方向": ("人工智能", "机器人", "低空经济", "Web3", "区块链", "算力", "芯片", "集成电路", "先进制造", "工业互联网"),
    "资金流向": ("专项债", "政府采购", "产业基金", "补贴", "贴息", "奖励资金", "中央预算", "税收优惠", "资金管理"),
    "创业机会": ("中小企业", "民营企业", "创新创业", "专精特新", "揭榜挂帅", "营商环境"),
    "就业与城市": ("高校毕业生", "粤港澳", "长三角", "京津冀"),
    "宏观环境": ("房地产", "民间投资", "货币政策", "经济增长"),
}

POLICY_WORDS = ("意见", "通知", "办法", "规定", "规划", "方案", "公告", "决定", "条例", "政策", "细则", "指南", "征求意见")
INTERPRETATION_WORDS = ("解读", "答记者问", "一图读懂", "图解")
NEWS_WORDS = ("会议召开", "调研", "会见", "活动举行", "工作动态", "新闻发布会")
IMPORTANT_WORDS = ("国务院", "中央", "专项债", "政府采购", "产业基金", "补贴", "贴息", "税收优惠", "准入", "监管", "实施条例", "管理办法", "行动方案")
MONEY_RE = re.compile(r"(?:\d+(?:\.\d+)?\s*(?:亿元|万元|万亿元)|专项债|中央预算内投资|政府采购|产业基金|补贴|贴息)")


def classify_status(title: str) -> str:
    if "征求意见" in title:
        return "draft"
    if any(word in title for word in INTERPRETATION_WORDS):
        return "interpretation"
    return "formal"


def is_policy_candidate(title: str) -> bool:
    if any(word in title for word in NEWS_WORDS) and not any(word in title for word in POLICY_WORDS):
        return False
    return any(word in title for word in POLICY_WORDS)


def detect_topics(title: str, content: str = "") -> list[str]:
    title_lower = title.lower()
    content_lower = content[:12000].lower()
    topics = []
    for topic, words in TOPIC_KEYWORDS.items():
        title_hit = any(word.lower() in title_lower for word in words)
        content_hits = sum(1 for word in words if word.lower() in content_lower)
        strong_hit = any(word.lower() in content_lower for word in STRONG_TOPIC_KEYWORDS[topic])
        if title_hit or strong_hit or content_hits >= 2:
            topics.append(topic)
    return topics


def score_policy(policy: PolicyDocument) -> tuple[int, str]:
    text = f"{policy.title}\n{policy.content[:16000]}"
    score = 35
    reasons: list[str] = []
    if policy.source_id == "gov_cn":
        score += 20
        reasons.append("国务院或国务院部门文件")
    if any(word in text for word in IMPORTANT_WORDS):
        score += 15
        reasons.append("包含重要政策工具或制度变化")
    if MONEY_RE.search(text):
        score += 15
        reasons.append("出现明确资金或资源配置线索")
    if policy.policy_status == "draft":
        score -= 8
        reasons.append("目前为征求意见稿")
    if len(policy.topics) >= 2:
        score += 8
        reasons.append("同时影响多个关注领域")
    return min(max(score, 0), 100), "；".join(reasons) or "与关注领域相关"
