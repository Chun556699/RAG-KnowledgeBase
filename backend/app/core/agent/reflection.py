"""
Agent 反思器。

对应需求「反思优化：具备自我评估和改进能力」。
在执行完计划后，调用 LLM 评估结果是否充分回答了原始问题，
输出「是否满意 + 理由 + 改进建议」，供执行器决定是否需要再一次迭代。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.llm.base import BaseLLMProvider, GenerationConfig, Message, Role
from app.core.llm.prompt import get_template
from app.utils.logger import get_logger
from app.utils.parsing import extract_json

logger = get_logger(__name__)


@dataclass
class Reflection:
    """
    反思结果。

    Attributes:
        satisfied: 结果是否令人满意。
        reason: 评价理由。
        suggestion: 改进建议（不满意时有效）。
    """

    satisfied: bool
    reason: str
    suggestion: str = ""


class Reflector:
    """反思器：评估执行结果质量。"""

    def __init__(self, llm: BaseLLMProvider) -> None:
        """
        Args:
            llm: 用于反思评估的 LLM 提供商。
        """
        self._llm = llm

    async def reflect(self, query: str, result: str) -> Reflection:
        """
        评估执行结果。

        Args:
            query: 原始问题。
            result: 当前得到的答案。

        Returns:
            Reflection: 反思结果；解析失败时默认视为满意，避免无意义的重试。
        """
        prompt = get_template("agent_reflection").render(query=query, result=result)
        messages = [Message(Role.USER, prompt)]
        resp = await self._llm.generate(messages, GenerationConfig(temperature=0.3))

        parsed = extract_json(resp.content)
        if isinstance(parsed, dict) and "satisfied" in parsed:
            reflection = Reflection(
                satisfied=bool(parsed.get("satisfied")),
                reason=str(parsed.get("reason", "")),
                suggestion=str(parsed.get("suggestion", "")),
            )
        else:
            # 解析失败时默认满意，防止陷入无限反思循环
            logger.warning("反思结果解析失败，默认视为满意")
            reflection = Reflection(satisfied=True, reason="无法解析评估结果，默认通过")

        logger.info("反思完成：satisfied=%s", reflection.satisfied)
        return reflection
