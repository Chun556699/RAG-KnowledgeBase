"""
Agent 执行器（编排核心）。

对应需求「决策执行：根据上下文做出智能决策」，将规划、工具调用、
答案汇总、反思优化串联为完整的 Agent 循环：

    规划(Planner) → 逐步执行(Tool / LLM) → 汇总(Synthesize)
        → 反思(Reflector) → [不满意则带建议再迭代一次]

整个过程产出结构化的执行轨迹（trace），便于前端可视化「智能体思考过程」。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from app.core.agent.planner import Planner, SubTask
from app.core.agent.reflection import Reflector
from app.core.agent.tools import ToolRegistry
from app.core.llm.base import BaseLLMProvider, GenerationConfig, Message, Role
from app.core.llm.prompt import get_template
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class StepResult:
    """单个子任务的执行结果（ReAct：推理 Thought → 行动 Action → 观察 Observation）。"""

    step: int
    description: str
    tool: Optional[str]
    output: str
    thought: str = ""


@dataclass
class AgentResult:
    """
    Agent 完整执行结果。

    Attributes:
        query: 原始问题。
        plan: 规划出的子任务列表。
        steps: 各步骤执行结果。
        answer: 汇总后的最终答案。
        reflection: 反思评价文本。
        iterations: 实际迭代轮数。
    """

    query: str
    plan: List[SubTask]
    steps: List[StepResult] = field(default_factory=list)
    answer: str = ""
    reflection: str = ""
    iterations: int = 1


class AgentExecutor:
    """Agent 执行器：编排规划-执行-反思闭环。"""

    def __init__(
        self,
        llm: BaseLLMProvider,
        tools: ToolRegistry,
        max_iterations: int = 2,
    ) -> None:
        """
        Args:
            llm: Agent 使用的 LLM 提供商。
            tools: 工具注册中心。
            max_iterations: 反思后允许的最大迭代次数（含首轮）。
        """
        self._llm = llm
        self._tools = tools
        self._planner = Planner(llm)
        self._reflector = Reflector(llm)
        self._max_iterations = max_iterations

    async def run(self, query: str) -> AgentResult:
        """
        执行完整 Agent 流程。

        Args:
            query: 用户复杂查询。

        Returns:
            AgentResult: 包含规划、步骤、答案与反思的完整结果。
        """
        # 1) 任务规划
        plan = await self._planner.plan(query, self._tools.describe())
        result = AgentResult(query=query, plan=plan)

        extra_hint = ""  # 反思后附加给下一轮的改进提示
        for iteration in range(1, self._max_iterations + 1):
            result.iterations = iteration

            # 2) 逐步执行子任务
            steps = await self._execute_steps(plan, extra_hint)
            result.steps = steps

            # 3) 汇总最终答案
            result.answer = await self._synthesize(query, steps)

            # 4) 反思评估
            reflection = await self._reflector.reflect(query, result.answer)
            result.reflection = reflection.reason

            if reflection.satisfied or iteration >= self._max_iterations:
                break

            # 5) 不满意则携带改进建议，进入下一轮迭代
            logger.info("反思未通过，携带建议进行第 %d 轮迭代", iteration + 1)
            extra_hint = f"\n上一轮的改进建议：{reflection.suggestion}"

        return result

    async def _execute_steps(
        self, plan: List[SubTask], extra_hint: str
    ) -> List[StepResult]:
        """按计划逐步执行：有工具则调工具，否则交给 LLM 直接作答。"""
        steps: List[StepResult] = []
        for task in plan:
            tool = self._tools.get(task.tool) if task.tool else None
            if tool is not None:
                # 决策：调用工具执行
                output = tool.run(task.description)
            else:
                # 决策：无合适工具，由 LLM 直接处理该子任务
                messages = [
                    Message(Role.SYSTEM, "你是一个执行子任务的助手，请简洁作答。"),
                    Message(Role.USER, task.description + extra_hint),
                ]
                resp = await self._llm.generate(
                    messages, GenerationConfig(temperature=0.5)
                )
                output = resp.content

            steps.append(
                StepResult(
                    step=task.step,
                    description=task.description,
                    tool=task.tool,
                    output=output,
                    thought=task.thought,
                )
            )
        return steps

    async def _synthesize(self, query: str, steps: List[StepResult]) -> str:
        """将各步骤结果汇总为连贯的最终答案。"""
        steps_text = "\n".join(
            f"步骤{s.step}（{s.tool or 'LLM'}）：{s.output}" for s in steps
        )
        prompt = get_template("agent_synthesize").render(query=query, steps=steps_text)
        messages = [Message(Role.USER, prompt)]
        resp = await self._llm.generate(messages, GenerationConfig(temperature=0.5))
        return resp.content
