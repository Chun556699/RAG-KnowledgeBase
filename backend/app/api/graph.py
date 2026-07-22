"""
知识图谱 API 路由。

暴露图谱的读取与重建接口：
- GET  /api/graph        读取当前已构建的图谱（节点/边）；
- POST /api/graph/build  触发从知识库语料重建图谱（调用 LLM 抽取实体关系）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.graph.builder import KnowledgeGraph
from app.models.schemas import (
    GraphBuildRequest,
    GraphEdgeSchema,
    GraphNodeSchema,
    GraphResponse,
)
from app.services.container import Container, get_container

router = APIRouter(prefix="/api/graph", tags=["graph"])


def _to_response(graph: KnowledgeGraph) -> GraphResponse:
    """将内部图谱数据结构转换为 API 响应模型。"""
    return GraphResponse(
        nodes=[
            GraphNodeSchema(id=n.id, label=n.label, weight=n.weight)
            for n in graph.nodes
        ],
        edges=[
            GraphEdgeSchema(
                source=e.source,
                target=e.target,
                relation=e.relation,
                weight=e.weight,
            )
            for e in graph.edges
        ],
        built_at=graph.built_at,
    )


@router.get("", response_model=GraphResponse, summary="获取知识图谱")
async def get_graph(
    container: Container = Depends(get_container),
) -> GraphResponse:
    """返回当前已构建的知识图谱；从未构建时节点与边均为空。"""
    return _to_response(container.graph.get_graph())


@router.post("/build", response_model=GraphResponse, summary="重建知识图谱")
async def build_graph(
    req: GraphBuildRequest,
    container: Container = Depends(get_container),
) -> GraphResponse:
    """
    从知识库全量语料重建知识图谱：采样片段 → LLM 抽取实体关系 → 聚合去重。

    该过程会调用 LLM，耗时与片段数、并发度相关；构建结果自动持久化。
    """
    graph = await container.graph.rebuild(
        provider=req.provider, model=req.model, max_chunks=req.max_chunks
    )
    return _to_response(graph)
