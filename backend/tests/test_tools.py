"""
Agent 工具测试。

覆盖计算器（含安全校验）、时间工具、知识库检索工具与工具注册中心。
"""

from __future__ import annotations

from app.core.agent.tools import (
    CalculatorTool,
    DateTimeTool,
    KnowledgeSearchTool,
    ToolRegistry,
)


def test_calculator_valid_expression():
    """合法算术表达式应正确求值。"""
    tool = CalculatorTool()
    result = tool.run("(128 + 56) * 3")
    assert "552" in result


def test_calculator_rejects_illegal_chars():
    """含非法字符（防代码注入）应被拒绝。"""
    tool = CalculatorTool()
    result = tool.run("__import__('os').system('ls')")
    assert "非法字符" in result


def test_calculator_handles_error():
    """除零等错误应被捕获而非抛出异常。"""
    tool = CalculatorTool()
    result = tool.run("1/0")
    assert "计算失败" in result


def test_datetime_tool():
    """时间工具应返回含当前年份的字符串。"""
    tool = DateTimeTool()
    result = tool.run("")
    assert "当前时间" in result


def test_knowledge_search_tool_with_result():
    """检索工具应调用注入的检索函数并包装结果。"""
    tool = KnowledgeSearchTool(search_fn=lambda q: f"命中内容:{q}")
    result = tool.run("向量检索")
    assert "知识库检索结果" in result
    assert "向量检索" in result


def test_knowledge_search_tool_empty():
    """检索无结果时应给出友好提示。"""
    tool = KnowledgeSearchTool(search_fn=lambda q: "")
    result = tool.run("不存在的内容")
    assert "未检索到" in result


def test_tool_registry():
    """注册中心应支持注册、按名获取与描述生成。"""
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(DateTimeTool())

    assert registry.get("calculator") is not None
    assert registry.get("not_exist") is None
    assert len(registry.list_tools()) == 2

    desc = registry.describe()
    assert "calculator" in desc
    assert "datetime" in desc
