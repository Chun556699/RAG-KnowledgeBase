"""
RAG 质量评估 API 路由。

暴露 RAGAS 风格的质量评估接口：输入「问题 + 回答 + 检索上下文」，
返回忠实度（faithfulness）与答案相关性（answer_relevancy）两个指标，
供前端评估面板 / 离线回归使用。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.evaluation.ragas import RagasEvaluator
from app.models.schemas import EvaluationRequest, EvaluationResponse
from app.services.container import Container, get_container

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


@router.post("", response_model=EvaluationResponse, summary="评估 RAG 回答质量")
async def evaluate(
    req: EvaluationRequest,
    container: Container = Depends(get_container),
) -> EvaluationResponse:
    """
    对一次 RAG 问答结果做质量评估。

    - faithfulness：回答是否忠于检索上下文（无编造）；\n    - answer_relevancy：回答是否切题、完整。\n    两个指标均为 LLM 打分（0~1），评估失败时对应指标降级为 0。
    """
    provider_name = req.provider or container.llm_factory.default_provider_name()
    llm = container.llm_factory.get_provider(provider_name)
    result = await RagasEvaluator.evaluate(llm, req.question, req.answer, req.context)
    return EvaluationResponse(**result)
