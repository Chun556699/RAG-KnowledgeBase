"""
Agent 服务。

对 AgentExecutor 的薄封装：根据请求选择 LLM 提供商，构造执行器并运行，
将结果适配为可序列化的结构。工具集来自全局注册中心（含知识库检索工具）。
"""

from __future__ import annotations

from typing import Optional

from app.config import Settings
from app.core.agent.executor import AgentExecutor, AgentResult
from app.core.agent.tools import ToolRegistry
from app.core.llm.factory import LLMFactory
from app.utils.logger import get_logger

logger = get_logger(__name__)


class AgentService:
    """智能体服务。"""

    def __init__(
        self,
        llm_factory: LLMFactory,
        tools: ToolRegistry,
        settings: Settings,
    ) -> None:
        self._llm_factory = llm_factory
        self._tools = tools
        self._settings = settings

    async def run(
        self,
        query: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> AgentResult:
        """
        运行一次完整的 Agent 任务。

        Args:
            query: 用户复杂查询。
            provider: LLM 提供商（覆盖默认）。
            model: 模型名（覆盖默认）。

        Returns:
            AgentResult: 规划、执行、汇总、反思的完整结果。
        """
        provider_name = provider or self._llm_factory.default_provider_name()
        llm = self._llm_factory.get_provider(provider_name, model)
        executor = AgentExecutor(llm, self._tools)
        logger.info("Agent 开始处理: %s", query[:40])
        return await executor.run(query)
