"""
LLM 输出解析工具测试。

验证 extract_json 在纯 JSON、代码块包裹、噪声干扰、非法输入下的健壮性。
"""

from __future__ import annotations

from app.utils.parsing import extract_json


def test_parse_plain_object():
    """可直接解析的 JSON 对象。"""
    assert extract_json('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}


def test_parse_plain_array():
    """可直接解析的 JSON 数组。"""
    assert extract_json("[1, 2, 3]") == [1, 2, 3]


def test_parse_from_code_fence():
    """应能从 ```json 代码块中抽取 JSON。"""
    text = '这是规划结果：\n```json\n{"steps": [1, 2]}\n```\n以上。'
    assert extract_json(text) == {"steps": [1, 2]}


def test_parse_from_noisy_text():
    """应能从自然语言包裹的噪声文本中定位 JSON。"""
    text = '好的，我的计划是 {"step": 1, "tool": "calculator"} 就这样。'
    assert extract_json(text) == {"step": 1, "tool": "calculator"}


def test_parse_invalid_returns_none():
    """无 JSON 内容应返回 None。"""
    assert extract_json("这里完全没有 JSON") is None


def test_parse_empty_returns_none():
    """空字符串应返回 None。"""
    assert extract_json("") is None
