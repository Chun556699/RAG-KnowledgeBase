"""
Agent 任务规划器。

对应需求「任务规划：能够分解复杂查询为多个子任务」。
调用 LLM 将用户复杂请求拆解为有序子任务列表；当 LLM 输出无法解析时，
退化为「单步兜底计划」，保证 Agent 流程健壮不中断。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from app.core.llm.base import BaseLLMProvider, GenerationConfig, Message, Role
from app.core.llm.prompt import get_template
from app.utils.logger import get_logger
from app.utils.parsing import extract_json

logger = get_logger(__name__)


@dataclass
class SubTask:
    """
    子任务（ReAct 风格：显式携带推理依据）。

    Attributes:
        step: 步骤序号（从 1 开始）。
        thought: 规划该步骤时的推理依据（Reasoning），解释「为什么要做这一步」。
        description: 子任务描述（Action）。
        tool: 建议调用的工具名，None 表示由 LLM 直接作答。
    """

    step: int
    description: str
    tool: Optional[str] = None
    thought: str = ""


class Planner:
    """任务规划器：将复杂查询分解为子任务。"""

    def __init__(self, llm: BaseLLMProvider) -> None:
        """
        Args:
            llm: 用于规划的 LLM 提供商。
        """
        self._llm = llm

    async def plan(self, query: str, tools_desc: str) -> List[SubTask]:
        """
        生成子任务列表。

        Args:
            query: 用户原始请求。
            tools_desc: 可用工具描述（注入提示词）。

        Returns:
            List[SubTask]: 有序子任务列表；解析失败时返回单步兜底计划。
        """
        prompt = get_template("agent_planner").render(query=query, tools=tools_desc)
        messages = [Message(Role.USER, prompt)]
        # 规划要求稳定，使用较低温度
        resp = await self._llm.generate(messages, GenerationConfig(temperature=0.2))

        parsed = extract_json(resp.content)
        subtasks = self._parse_subtasks(parsed)

        if not subtasks:
            # 兜底：无法解析出计划时，退化为「直接检索知识库并回答」的单步计划
            logger.warning("规划结果解析失败，使用单步兜底计划")
            subtasks = [
                SubTask(
                    step=1,
                    description=query,
                    tool="knowledge_search",
                    thought="无法拆解为多步，直接检索知识库以回答原始问题。",
                )
            ]
        logger.info("任务规划完成，共 %d 个子任务", len(subtasks))
        return subtasks

    @staticmethod
    def _parse_subtasks(parsed: object) -> List[SubTask]:
        """将解析出的 JSON 转换为 SubTask 列表，容忍字段缺失。"""
        if not isinstance(parsed, list):
            return []
        subtasks: List[SubTask] = []
        for i, item in enumerate(parsed, start=1):
            if not isinstance(item, dict):
                continue
            desc = str(item.get("description", "")).strip()
            if not desc:
                continue
            tool = item.get("tool")
            # 规划器可能输出字符串 "null"，统一归一为 None
            if isinstance(tool, str) and tool.lower() in ("null", "none", ""):
                tool = None
            subtasks.append(
                SubTask(
                    step=int(item.get("step", i)),
                    description=desc,
                    tool=tool,
                    thought=str(item.get("thought", "")).strip(),
                )
            )
        return subtasks
