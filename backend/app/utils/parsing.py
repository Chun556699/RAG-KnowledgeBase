"""
LLM 输出解析工具。

大模型返回的 JSON 常被包裹在自然语言或 ```json 代码块中。
本模块提供健壮的 JSON 抽取，容忍这些噪声，用于 Agent 规划/反思结果解析。
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional


def extract_json(text: str) -> Optional[Any]:
    """
    从可能含噪声的文本中抽取首个合法 JSON（对象或数组）。

    处理策略：
    1. 优先解析 ```json ... ``` 代码块；
    2. 否则在全文中定位首个 { 或 [ 到匹配结尾的子串尝试解析；
    3. 全部失败返回 None。

    Args:
        text: LLM 原始输出文本。

    Returns:
        Optional[Any]: 解析出的 Python 对象（dict/list），失败为 None。
    """
    if not text:
        return None

    # 1) 优先匹配 markdown 代码块中的 JSON
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    candidates = []
    if fence:
        candidates.append(fence.group(1).strip())
    candidates.append(text.strip())

    for candidate in candidates:
        parsed = _try_parse_first_json(candidate)
        if parsed is not None:
            return parsed
    return None


def _try_parse_first_json(text: str) -> Optional[Any]:
    """尝试从文本中定位并解析首个 JSON 值。"""
    # 直接尝试整体解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 定位首个 { 或 [，向后扩展寻找可解析的子串
    start_candidates = [i for i, ch in enumerate(text) if ch in "{["]
    for start in start_candidates:
        for end in range(len(text), start, -1):
            snippet = text[start:end]
            try:
                return json.loads(snippet)
            except json.JSONDecodeError:
                continue
    return None
