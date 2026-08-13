"""
检索质量评估模块（CRAG - Corrective RAG 纠正性检索）。

解决「检索回来了，但内容跑偏」的问题：用 LLM 对检索结果做一次质量评估，
判断其是否足以回答用户问题；若不足，则生成一个更优的检索查询供上层重新检索。
这是 Corrective RAG 的核心：先评估、再纠正，从而在检索质量不佳时自动补救，
而不是把跑偏的上下文直接交给生成模型。

设计要点：
- 评估失败 / JSON 解析失败时默认「充分」，绝不阻断主问答流程（健壮性优先）；
- 仅返回结构化评估结论，检索纠正动作由上层（ChatService）执行，职责单一。
"""

from __future__ import annotations

from typing import Dict

from app.core.llm.base import BaseLLMProvider, GenerationConfig, Message, Role
from app.core.llm.prompt import get_template
from app.utils.logger import get_logger
from app.utils.parsing import extract_json

logger = get_logger(__name__)


class RetrievalEvaluator:
    """用 LLM 评估检索结果质量（CRAG 的评估环节）。"""

    @staticmethod
    async def evaluate(
        llm: BaseLLMProvider,
        query: str,
        context: str,
    ) -> Dict[str, str | bool]:
        """
        评估检索上下文是否足以回答查询。

        Args:
            llm: 已解析的 LLM 提供商实例（复用主问答的 LLM）。
            query: 用户查询。
            context: 检索到的上下文文本（为空时传空串）。

        Returns:
            Dict: 含 sufficient(bool) / reason(str) / rewritten_query(str)。
            评估失败时默认 sufficient=True（不阻断主流程）。
        """
        prompt = get_template("retrieval_eval").render(
            query=query, context=context or "（无检索结果）"
        )
        try:
            resp = await llm.generate(
                [Message(Role.USER, prompt)],
                GenerationConfig(temperature=0.0, max_tokens=256),
            )
            data = extract_json(resp.content or "")
        except Exception as exc:  # noqa: BLE001 评估失败不阻断主流程
            logger.warning("检索质量评估失败，默认视为充分: %s", exc)
            return {"sufficient": True, "reason": "", "rewritten_query": ""}

        if isinstance(data, dict):
            return {
                "sufficient": bool(data.get("sufficient", True)),
                "reason": str(data.get("reason", "")),
                "rewritten_query": str(data.get("rewritten_query", "")).strip(),
            }
        logger.warning("检索质量评估结果解析失败，默认视为充分")
        return {"sufficient": True, "reason": "", "rewritten_query": ""}
