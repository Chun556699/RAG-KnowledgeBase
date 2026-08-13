"""
CRAG 检索质量评估器测试。

覆盖：充分/不充分判定、JSON 解析失败与 LLM 调用失败时的健壮降级。
"""

from __future__ import annotations

from app.core.llm.base import LLMResponse
from app.core.rag.evaluator import RetrievalEvaluator


class FakeLLM:
    """返回固定文本的假 LLM（仅实现 generate）。"""

    name = "fake"
    model = "fake-model"

    def __init__(self, text: str) -> None:
        self._text = text

    async def generate(self, messages, config=None) -> LLMResponse:
        return LLMResponse(content=self._text, model="fake", provider="fake")


async def test_evaluate_sufficient():
    """评估为充分时应返回 sufficient=True。"""
    llm = FakeLLM('{"sufficient": true, "reason": "资料充分", "rewritten_query": ""}')
    result = await RetrievalEvaluator.evaluate(llm, "问题", "上下文")
    assert result["sufficient"] is True
    assert result["rewritten_query"] == ""


async def test_evaluate_insufficient():
    """评估为不充分时应返回 sufficient=False 与更优查询。"""
    llm = FakeLLM(
        '{"sufficient": false, "reason": "资料不足", "rewritten_query": "更好的查询"}'
    )
    result = await RetrievalEvaluator.evaluate(llm, "问题", "上下文")
    assert result["sufficient"] is False
    assert result["rewritten_query"] == "更好的查询"


async def test_evaluate_parse_failure_defaults_sufficient():
    """JSON 解析失败时应默认充分（不阻断主流程）。"""
    llm = FakeLLM("这不是 JSON")
    result = await RetrievalEvaluator.evaluate(llm, "问题", "上下文")
    assert result["sufficient"] is True


async def test_evaluate_llm_error_defaults_sufficient():
    """LLM 调用失败时应默认充分（不阻断主流程）。"""

    class _BadLLM:
        async def generate(self, messages, config=None):
            raise RuntimeError("boom")

    result = await RetrievalEvaluator.evaluate(_BadLLM(), "问题", "上下文")
    assert result["sufficient"] is True
