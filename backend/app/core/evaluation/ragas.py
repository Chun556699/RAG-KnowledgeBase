"""
RAG 质量评估模块（RAGAS 风格）。

提供 RAG 回答质量的自动评估指标，参考 RAGAS 的核心思想：
- **faithfulness（忠实度）**：回答是否忠于检索上下文，是否存在编造（幻觉）；
- **answer_relevancy（答案相关性）**：回答是否直接、完整地回应了问题。

指标均由 LLM 打分（0~1），供评估端点 / 前端面板使用，也可用于离线回归。
任何 LLM 调用或解析失败都返回 0.0（健壮降级，不阻断主流程）。
"""

from __future__ import annotations

from typing import Dict

from app.core.llm.base import BaseLLMProvider, GenerationConfig, Message, Role
from app.core.llm.prompt import get_template
from app.utils.logger import get_logger
from app.utils.parsing import extract_json

logger = get_logger(__name__)


class RagasEvaluator:
    """RAGAS 风格的质量评估器。"""

    @staticmethod
    async def _score(llm: BaseLLMProvider, prompt: str) -> float:
        """调用 LLM 打分，解析失败或异常时返回 0.0。"""
        try:
            resp = await llm.generate(
                [Message(Role.USER, prompt)],
                GenerationConfig(temperature=0.0, max_tokens=256),
            )
            data = extract_json(resp.content or "")
            if isinstance(data, dict) and "score" in data:
                score = float(data["score"])
                return max(0.0, min(1.0, score))
        except Exception as exc:  # noqa: BLE001  评估失败不阻断主流程
            logger.warning("RAGAS 打分失败，返回 0.0: %s", exc)
        return 0.0

    @classmethod
    async def evaluate_faithfulness(
        cls, llm: BaseLLMProvider, question: str, answer: str, context: str
    ) -> float:
        """评估回答对检索上下文的忠实度（0~1）。"""
        prompt = get_template("ragas_faithfulness").render(
            question=question, answer=answer, context=context or "（无）"
        )
        return await cls._score(llm, prompt)

    @classmethod
    async def evaluate_answer_relevancy(
        cls, llm: BaseLLMProvider, question: str, answer: str
    ) -> float:
        """评估回答与问题的相关性（0~1）。"""
        prompt = get_template("ragas_answer_relevancy").render(
            question=question, answer=answer
        )
        return await cls._score(llm, prompt)

    @classmethod
    async def evaluate(
        cls, llm: BaseLLMProvider, question: str, answer: str, context: str = ""
    ) -> Dict[str, float]:
        """
        综合评估，返回忠实度与答案相关性。

        Args:
            llm: LLM 提供商实例。
            question: 用户问题。
            answer: 系统回答。
            context: 检索到的上下文（忠实度评估需要）。

        Returns:
            Dict[str, float]: {"faithfulness": float, "answer_relevancy": float}。
        """
        faithfulness = await cls.evaluate_faithfulness(llm, question, answer, context)
        relevancy = await cls.evaluate_answer_relevancy(llm, question, answer)
        return {
            "faithfulness": round(faithfulness, 3),
            "answer_relevancy": round(relevancy, 3),
        }
