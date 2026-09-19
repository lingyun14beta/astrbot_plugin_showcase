"""消息规则匹配与模糊匹配的纯逻辑。

这里刻意**不 import 任何 astrbot 模块**，因此可以在没装 AstrBot 的环境里直接单测
（见 ``tests/test_rules.py``，CI 里跑的就是它），也方便在别处复用。
``main.py`` 里的过滤器与指令只是调用这些函数，不再自己实现算法。
"""

from __future__ import annotations

import difflib
import re


def keyword_coverage(keyword: str, text: str) -> float:
    """计算关键词被消息连续覆盖的比例。

    用「关键词在消息里能连续匹配到的长度 / 关键词长度」而不是整条消息与关键词的整体相似度：
    后者在带指令词的长消息上会被稀释，比如 ``/showcase-fuzzy`` 与 ``showcase`` 只有 0.70。

    Args:
        keyword: 关键词（调用方负责先小写化）。
        text: 消息文本（调用方负责先小写化）。

    Returns:
        0~1 的比例；关键词为空时返回 0.0。
    """
    if not keyword:
        return 0.0
    matcher = difflib.SequenceMatcher(None, keyword, text)
    matched = matcher.find_longest_match(0, len(keyword), 0, len(text)).size
    return matched / len(keyword)


def fuzzy_hit(keywords: list[str], text: str, threshold: float) -> bool:
    """消息与任一关键词达到模糊匹配阈值时为 True。

    Args:
        keywords: 配置里的关键词列表。
        text: 原始消息文本。
        threshold: 0~1 的阈值。

    Returns:
        是否命中。
    """
    normalized = text.strip().lower()
    if not normalized:
        return False
    return any(
        keyword_coverage(str(keyword).strip().lower(), normalized) >= threshold
        for keyword in keywords
        if str(keyword).strip()
    )


def match_reply(rules: list[dict], text: str) -> str | None:
    """按 ``template_list`` 规则匹配消息，返回命中的回复文本。

    正则规则按 ``priority`` 从高到低匹配，其次才是关键词规则；无效正则会被跳过
    （有效性由 :func:`invalid_regexes` 在加载时检查并记录日志）。

    Args:
        rules: 配置里的规则列表，元素用 ``__template_key`` 区分模板。
        text: 消息文本。

    Returns:
        命中的回复内容；没有规则命中时返回 None。
    """
    regex_rules = sorted(
        (r for r in rules if r.get("__template_key") == "regex"),
        key=lambda r: int(r.get("priority", 0) or 0),
        reverse=True,
    )
    for rule in regex_rules:
        expression = str(rule.get("expression", "")).strip()
        if not expression:
            continue
        try:
            if re.search(expression, text):
                return str(rule.get("reply", "")).strip() or None
        except re.error:
            continue

    for rule in rules:
        if rule.get("__template_key") != "keyword":
            continue
        pattern = str(rule.get("pattern", "")).strip()
        if not pattern:
            continue
        hit = (
            pattern in text
            if rule.get("case_sensitive")
            else pattern.lower() in text.lower()
        )
        if hit:
            return str(rule.get("reply", "")).strip() or None
    return None


def invalid_regexes(rules: list[dict]) -> list[str]:
    """列出配置里无法编译的正则表达式。

    Args:
        rules: 配置里的规则列表。

    Returns:
        无效的正则字符串列表；全部合法时为空列表。
    """
    broken: list[str] = []
    for rule in rules:
        if rule.get("__template_key") != "regex":
            continue
        expression = str(rule.get("expression", "")).strip()
        if not expression:
            continue
        try:
            re.compile(expression)
        except re.error:
            broken.append(expression)
    return broken
