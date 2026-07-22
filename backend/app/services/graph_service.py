"""
知识图谱服务。

对 API 层暴露图谱的读取与重建能力，编排 KnowledgeGraphBuilder：
- get_graph()：读取已持久化的图谱（内存缓存优先）；
- rebuild()：异步重建图谱，用锁防止并发重复构建。
"""

from __future__ import annotations

import asyncio
from typing import Optional

from app.config import Settings
from app.core.graph.builder import KnowledgeGraph, KnowledgeGraphBuilder
from app.core.llm.factory import LLMFactory
from app.core.rag.retriever import Retriever
from app.utils.logger import get_logger

logger = get_logger(__name__)


class GraphService:
    """知识图谱高层服务。"""

    def __init__(
        self,
        llm_factory: LLMFactory,
        retriever: Retriever,
        settings: Settings,
    ) -> None:
        self._builder = KnowledgeGraphBuilder(llm_factory, retriever, settings)
        self._lock = asyncio.Lock()
        # 内存缓存：首次访问时从磁盘惰性加载
        self._cache: Optional[KnowledgeGraph] = None

    def get_graph(self) -> KnowledgeGraph:
        """返回当前图谱（缓存未命中则从磁盘加载）。"""
        if self._cache is None:
            self._cache = self._builder.load()
        return self._cache

    async def rebuild(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        max_chunks: Optional[int] = None,
    ) -> KnowledgeGraph:
        """
        重建知识图谱。用锁串行化，避免并发重复构建浪费 LLM 调用。

        Args:
            provider: LLM 提供商，覆盖默认值。
            model: 模型名，覆盖默认值。
            max_chunks: 本次最多参与抽取的片段数。

        Returns:
            KnowledgeGraph: 重建后的图谱。
        """
        async with self._lock:
            graph = await self._builder.build(
                provider=provider, model=model, max_chunks=max_chunks
            )
            self._cache = graph
            return graph
