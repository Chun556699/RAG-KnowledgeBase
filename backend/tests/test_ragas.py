"""
RAGAS 风格质量评估测试。

覆盖忠实度 / 答案相关性的打分与健壮降级。
"""

from __future__ import annotations

from app.core.evaluation.ragas import RagasEvaluator
from app.core.llm.base import LLMResponse


class FakeLLM:
    """返回固定 JSON 的假 LLM。"""

    name = "fake"
    model = "fake-model"

    def __init__(self, text: str) -> None:
        self._text = text

    async def generate(self, messages, config=None) -> LLMResponse:
        return LLMResponse(content=self._text, model="fake", provider="fake")


async def test_evaluate_faithfulness():
    """忠实度评估应返回 LLM 给出的分数。"""
    llm = FakeLLM('{"score": 0.85, "reason": "回答基本忠于上下文"}')
    score = await RagasEvaluator.evaluate_faithfulness(llm, "问题", "回答", "上下文")
    assert score == 0.85


async def test_evaluate_answer_relevancy():
    """答案相关性评估应返回 LLM 给出的分数。"""
    llm = FakeLLM('{"score": 0.9, "reason": "回答切题"}')
    score = await RagasEvaluator.evaluate_answer_relevancy(llm, "问题", "回答")
    assert score == 0.9


async def test_evaluate_combined():
    """综合评估应返回两个指标。"""
    llm = FakeLLM('{"score": 0.7, "reason": "ok"}')
    result = await RagasEvaluator.evaluate(llm, "问题", "回答", "上下文")
    assert result["faithfulness"] == 0.7
    assert result["answer_relevancy"] == 0.7


async def test_evaluate_clamps_score():
    """分数应被限制在 [0, 1] 区间。"""
    llm = FakeLLM('{"score": 5.0, "reason": "越界"}')
    score = await RagasEvaluator.evaluate_faithfulness(llm, "问题", "回答", "上下文")
    assert score == 1.0


async def test_evaluate_parse_failure_returns_zero():
    """解析失败时应返回 0.0。"""
    llm = FakeLLM("不是 JSON")
    score = await RagasEvaluator.evaluate_faithfulness(llm, "问题", "回答", "上下文")
    assert score == 0.0
