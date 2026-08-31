"""月份的解析、中文标签与分组工具（收藏夹 / 历史记录共用）。"""
from __future__ import annotations

from datetime import datetime
from typing import List

# 设计稿只显示"八月""七月"；跨年时补上年份
_CN = ["一月", "二月", "三月", "四月", "五月", "六月",
       "七月", "八月", "九月", "十月", "十一月", "十二月"]


def month_key_of(date_str: str | None, fallback=None) -> str:
    """从日期字符串取 'YYYY-MM'；解析失败返回 fallback。"""
    if date_str:
        try:
            return date_str[:7]
        except Exception:  # noqa: BLE001
            pass
    return fallback


def month_key_of_ts(timestamp: float | None) -> str | None:
    """从时间戳取 'YYYY-MM'。"""
    if timestamp:
        try:
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m")
        except Exception:  # noqa: BLE001
            pass
    return None


def cn_month_label(key: str, now_year: str | None = None) -> str:
    """把 'YYYY-MM' 转成 '8月' / '2025年8月' 之类的标签。"""
    try:
        year, month = (int(x) for x in key.split("-"))
    except (ValueError, AttributeError):
        return key
    month_cn = _CN[month - 1] if 1 <= month <= 12 else f"{month}月"
    label = month_cn
    # 设计稿默认同一年只显示"八月"，跨年才带年份
    if now_year is None:
        now_year = datetime.now().year
    if year != now_year:
        label = f"{year}年{month_cn}"
    return label.replace("月月", "月")


def cn_month_label_cn(key: str) -> str:
    """'YYYY-MM' → '8月'（不带年份），用于时间轴标题。"""
    try:
        _, month = (int(x) for x in key.split("-"))
    except (ValueError, AttributeError):
        return key
    return _CN[month - 1] if 1 <= month <= 12 else f"{month}月"


def match_date(query: str, key: str | None, date_str: str = "") -> bool:
    """日期搜索：query 命中月份键或日期字符串即通过。"""
    q = (query or "").strip()
    if not q:
        return True
    if key and q in key:
        return True
    if q in date_str:
        return True
    # 支持 "8月"、"2026年8月" 之类的自然输入
    return q in (key or "") or q in date_str


def group_by_month(items: List[dict], key_field: str = "month") -> List[dict]:
    """把 [{month, ...}] 按月份分组，返回 [{month, label, items}]，月份倒序。"""
    buckets: dict[str, list] = {}
    for it in items:
        buckets.setdefault(it.get(key_field), []).append(it)
    groups = []
    for month, its in buckets.items():
        groups.append(
            {
                "month": month,
                "label": cn_month_label(month),
                "items": its,
            }
        )
    groups.sort(key=lambda g: g["month"] or "", reverse=True)
    return groups
