"""
Agent API 路由。

暴露智能体任务执行接口：接收复杂查询，返回规划、执行步骤、
最终答案与反思评价的完整轨迹，便于前端可视化 Agent 思考过程。
另提供工具清单查询接口。
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends

from app.models.schemas import (
    AgentRequest,
    AgentResponse,
    StepResultSchema,
    SubTaskSchema,
)
from app.services.container import Container, get_container

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("", response_model=AgentResponse, summary="运行智能体任务")
async def run_agent(
    req: AgentRequest,
    container: Container = Depends(get_container),
) -> AgentResponse:
    """
    提交一个复杂查询，Agent 将自动完成：
    任务规划 → 工具调用/推理 → 结果汇总 → 自我反思（必要时迭代）。
    """
    result = await container.agent.run(
        query=req.query, provider=req.provider, model=req.model
    )
    return AgentResponse(
        query=result.query,
        plan=[
            SubTaskSchema(
                step=t.step,
                thought=t.thought,
                description=t.description,
                tool=t.tool,
            )
            for t in result.plan
        ],
        steps=[
            StepResultSchema(
                step=s.step,
                thought=s.thought,
                description=s.description,
                tool=s.tool,
                output=s.output,
            )
            for s in result.steps
        ],
        answer=result.answer,
        reflection=result.reflection,
        iterations=result.iterations,
    )


@router.get("/tools", summary="列出可用工具")
async def list_tools(
    container: Container = Depends(get_container),
) -> List[dict]:
    """返回 Agent 当前可调用的工具清单。"""
    return [
        {"name": t.name, "description": t.description}
        for t in container.tools.list_tools()
    ]
