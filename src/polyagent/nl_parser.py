from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone


def _extract_numeric_threshold(text: str, aliases: list[str], default: int) -> int:
    alias_pattern = "|".join(re.escape(alias) for alias in aliases)
    patterns = [
        rf"(?:{alias_pattern})\s*(?:>=|>|不少于|至少|不低于)?\s*(\d+(?:\.\d+)?)([kKmMwW万]?)",
        rf"(\d+(?:\.\d+)?)([kKmMwW万]?)\s*(?:以上|起|and up)?\s*(?:{alias_pattern})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            number = float(match.group(1))
            unit = match.group(2).lower()
            if unit in {"k"}:
                number *= 1_000
            elif unit in {"m", "w", "万"}:
                number *= 1_000_000 if unit == "m" else 10_000
            return int(number)
    return default


def parse_natural_language_to_market_query(text: str) -> dict[str, str | int | float | bool]:
    lower = text.strip().lower()
    params: dict[str, str | int | float | bool] = {"active": True, "closed": False}

    tag_synonyms: dict[str, list[str]] = {
        "china": ["china", "中国", "中美", "beijing"],
        "election": ["election", "选举", "投票", "大选"],
        "war": ["war", "战争", "冲突", "军事"],
        "bitcoin": ["bitcoin", "btc", "比特币", "crypto", "加密货币"],
        "fed": ["fed", "fomc", "美联储", "利率决议"],
    }

    scored_tags: dict[str, int] = {}
    for tag, synonyms in tag_synonyms.items():
        score = sum(1 for synonym in synonyms if synonym in lower)
        if score > 0:
            scored_tags[tag] = score

    if scored_tags:
        params["tag_slug"] = max(scored_tags, key=scored_tags.get)

    liquidity_terms = ["liquidity", "流动性", "深度"]
    volume_terms = ["volume", "成交量", "交易量"]

    high_liquidity_words = ["高流动性", "high liquidity", "deep market", "流动性好"]
    high_volume_words = ["高成交", "high volume", "大成交", "成交活跃"]

    if any(word in lower for word in high_liquidity_words) or any(term in lower for term in liquidity_terms):
        params["liquidity_min"] = _extract_numeric_threshold(lower, liquidity_terms, 100000)

    if any(word in lower for word in high_volume_words) or any(term in lower for term in volume_terms):
        params["volume_min"] = _extract_numeric_threshold(lower, volume_terms, 1000000)

    trending_words = ["最近爆火", "trending", "updated", "热度", "飙升", "spike"]
    if any(word in lower for word in trending_words):
        params["order"] = "updatedAt"
        params["ascending"] = False

    ending_words = ["即将结束", "ending soon", "快到期", "near expiry", "临近结算"]
    if any(word in lower for word in ending_words):
        horizon_hours = 48
        hours_match = re.search(r"(\d{1,3})\s*(?:小时|h|hours)", lower)
        days_match = re.search(r"(\d{1,2})\s*(?:天|d|days)", lower)
        if hours_match:
            horizon_hours = int(hours_match.group(1))
        elif days_match:
            horizon_hours = int(days_match.group(1)) * 24
        params["end_date_max"] = (datetime.now(timezone.utc) + timedelta(hours=horizon_hours)).isoformat()

    if "最新" in lower or "latest" in lower:
        params.setdefault("order", "updatedAt")
        params.setdefault("ascending", False)

    return params
