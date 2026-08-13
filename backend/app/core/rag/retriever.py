"""
检索器模块。

将「文档摄取（索引构建）」与「语义检索」封装为高层 API，
是 RAG 系统对上层业务暴露的主入口。内部编排：加载 → 分块 → 嵌入 → 入库 / 检索。
"""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from app.core.rag.embeddings import BaseEmbedder
from app.core.rag.reranker import BaseReranker, NoOpReranker
from app.core.rag.sparse import BM25Index
from app.core.rag.splitter import TextSplitter
from app.core.rag.vectorstore import RetrievedChunk, VectorStore
from app.utils.logger import get_logger

logger = get_logger(__name__)


class Retriever:
    """RAG 检索器：负责索引构建与语义检索（可选两阶段重排序）。"""

    def __init__(
        self,
        vector_store: VectorStore,
        splitter: TextSplitter,
        reranker: Optional[BaseReranker] = None,
        candidate_k: int = 20,
        sparse_index: Optional[BM25Index] = None,
        hybrid_enabled: bool = True,
        rrf_k: int = 60,
        dense_weight: float = 1.0,
        sparse_weight: float = 1.0,
    ) -> None:
        """
        Args:
            vector_store: 向量存储实例。
            splitter: 文本分块器实例。
            reranker: 重排序器，为 None 时不启用（等价于 NoOp）。
            candidate_k: 启用重排序/混合检索时，第一阶段召回的候选片段数。
            sparse_index: BM25 稀疏索引；提供且 hybrid_enabled=True 时启用混合检索。
            hybrid_enabled: 是否启用「向量 + 稀疏」混合检索。
            rrf_k: RRF（倒数排名融合）的平滑参数，越小排名影响越显著。
            dense_weight: RRF 中向量路的权重（语义场景可调高）。
            sparse_weight: RRF 中稀疏路的权重（精确匹配/专有名词场景可调高）。
        """
        self._store = vector_store
        self._splitter = splitter
        self._reranker: BaseReranker = reranker or NoOpReranker()
        self._candidate_k = candidate_k
        self._sparse = sparse_index
        self._hybrid = hybrid_enabled
        self._rrf_k = rrf_k
        self._dense_weight = dense_weight
        self._sparse_weight = sparse_weight

    def set_reranker(self, reranker: BaseReranker, candidate_k: Optional[int] = None) -> None:
        """热替换重排序器（配置变更后由容器调用），可同时更新候选召回数。"""
        self._reranker = reranker or NoOpReranker()
        if candidate_k is not None:
            self._candidate_k = candidate_k

    def set_embedder(self, embedder: BaseEmbedder) -> None:
        """热替换嵌入器（切换嵌入配置后由容器调用）。"""
        self._store.set_embedder(embedder)

    def index_document(
        self,
        document_id: str,
        filename: str,
        text: str,
    ) -> int:
        """
        对单个文档构建索引：分块并写入向量库。

        Args:
            document_id: 文档唯一 ID。
            filename: 原始文件名（存入元数据，便于溯源）。
            text: 文档纯文本内容。

        Returns:
            int: 生成并入库的片段数量。
        """
        chunks = self._splitter.split(text)
        if not chunks:
            logger.warning("文档 %s 分块为空，跳过索引", filename)
            return 0

        chunk_ids: List[str] = []
        texts: List[str] = []
        metadatas: List[Dict[str, str]] = []
        for chunk in chunks:
            chunk_ids.append(f"{document_id}:{chunk.index}:{uuid.uuid4().hex[:8]}")
            texts.append(chunk.text)
            metadatas.append(
                {
                    "document_id": document_id,
                    "filename": filename,
                    "chunk_index": str(chunk.index),
                }
            )

        self._store.add_chunks(chunk_ids, texts, metadatas)
        # 同步更新稀疏索引（混合检索用）
        if self._sparse is not None:
            for cid, t, m in zip(chunk_ids, texts, metadatas):
                self._sparse.add(cid, t, m)
        logger.info("文档 %s 索引完成，共 %d 个片段", filename, len(chunks))
        return len(chunks)

    def retrieve(
        self,
        query: str,
        top_k: int = 4,
        document_id: str | None = None,
        min_score: float = 0.0,
    ) -> List[RetrievedChunk]:
        """
        检索与查询最相关的片段（支持混合检索 + 可选重排序）。

        检索策略：
        1. 混合检索（默认）：向量稠密检索 + BM25 稀疏检索 → RRF 倒数排名融合；
        2. 若启用重排序，则在融合后再由 Cross-Encoder 精排；
        3. 最后按 min_score 过滤噪音。任一路失败都会降级而不阻断主流程。

        Args:
            query: 查询文本。
            top_k: 返回条数。
            document_id: 若指定，则仅在该文档范围内检索。
            min_score: 相关性阈值，低于此分数的片段视为噪音被过滤。

        Returns:
            List[RetrievedChunk]: 相关片段列表（可能为空）。
        """
        where = {"document_id": document_id} if document_id else None

        # 混合检索：向量 + 稀疏 → RRF 融合
        if self._hybrid and self._sparse is not None:
            candidate_k = max(top_k, self._candidate_k)
            dense = self._store.query(
                query, top_k=candidate_k, where=where, min_score=0.0
            )
            sparse = self._sparse.search(query, top_k=candidate_k)
            if document_id:
                sparse = [
                    h for h in sparse
                    if h.metadata.get("document_id") == document_id
                ]
            fused = self._rrf_fuse(
                dense, sparse, top_k=top_k, k=self._rrf_k,
                dense_weight=self._dense_weight, sparse_weight=self._sparse_weight,
            )
            if self._reranker.enabled:
                fused = self._reranker.rerank(query, fused, top_n=top_k)
            results = [c for c in fused if c.score >= min_score]
            logger.info(
                "混合检索 '%s'：向量 %d + 稀疏 %d → 融合 %d（阈值=%.3f）",
                query[:30], len(dense), len(sparse), len(results), min_score,
            )
            return results

        # 纯向量检索（未启用混合检索时）：两阶段（召回 + 重排）
        if self._reranker.enabled:
            candidate_k = max(top_k, self._candidate_k)
            candidates = self._store.query(
                query, top_k=candidate_k, where=where, min_score=0.0
            )
            reranked = self._reranker.rerank(query, candidates, top_n=top_k)
            results = [c for c in reranked if c.score >= min_score]
            logger.info(
                "两阶段检索 '%s'：召回 %d → 重排后命中 %d（阈值=%.3f）",
                query[:30], len(candidates), len(results), min_score,
            )
            return results

        results = self._store.query(query, top_k=top_k, where=where, min_score=min_score)
        logger.info("检索 '%s' 命中 %d 个片段（阈值=%.3f）", query[:30], len(results), min_score)
        return results

    @staticmethod
    def _rrf_fuse(
        dense: List[RetrievedChunk],
        sparse: List,
        top_k: int,
        k: int = 60,
        dense_weight: float = 1.0,
        sparse_weight: float = 1.0,
    ) -> List[RetrievedChunk]:
        """
        RRF（Reciprocal Rank Fusion）倒数排名融合（支持两路加权）。

        将两路检索结果按各自排名累加 ``weight/(k + rank)``，使两路都命中的片段
        排名靠前；得分归一化到 0~1（1.0 = 两路均排名第一）。

        Args:
            dense: 向量检索结果（RetrievedChunk 列表）。
            sparse: 稀疏检索结果（SparseHit 列表，鸭子类型）。
            top_k: 融合后返回条数。
            k: 平滑参数。
            dense_weight: 向量路权重。
            sparse_weight: 稀疏路权重。

        Returns:
            List[RetrievedChunk]: 融合后的片段，score 为归一化 RRF 得分。
        """
        rrf: Dict[str, float] = {}
        by_id: Dict[str, RetrievedChunk] = {}
        for rank, c in enumerate(dense):
            rrf[c.chunk_id] = rrf.get(c.chunk_id, 0.0) + dense_weight / (k + rank + 1)
            by_id[c.chunk_id] = c
        for rank, h in enumerate(sparse):
            rrf[h.chunk_id] = rrf.get(h.chunk_id, 0.0) + sparse_weight / (k + rank + 1)
            if h.chunk_id not in by_id:
                by_id[h.chunk_id] = RetrievedChunk(
                    chunk_id=h.chunk_id,
                    text=h.text,
                    score=0.0,
                    metadata=h.metadata,
                )

        max_rrf = (dense_weight + sparse_weight) / (k + 1)  # 两路均第一名的理论上限
        ranked = sorted(rrf.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [
            RetrievedChunk(
                chunk_id=by_id[cid].chunk_id,
                text=by_id[cid].text,
                score=round(rrf_score / max_rrf, 4),
                metadata=by_id[cid].metadata,
            )
            for cid, rrf_score in ranked
        ]

    def delete_document(self, document_id: str) -> None:
        """删除某文档的全部索引片段。"""
        self._store.delete_by_document(document_id)
        if self._sparse is not None:
            self._sparse.remove_by_document(document_id)

    def count(self) -> int:
        """返回向量库中的片段总数。"""
        return self._store.count()

    def all_chunks(self) -> List[RetrievedChunk]:
        """返回向量库内全部片段（供知识图谱等全量遍历场景）。"""
        return self._store.all_chunks()

    @staticmethod
    def build_context(chunks: List[RetrievedChunk]) -> str:
        """
        将检索片段拼接为可注入提示词的上下文文本。

        Args:
            chunks: 检索到的片段列表。

        Returns:
            str: 带编号来源标注的上下文字符串。
        """
        if not chunks:
            return ""
        parts = []
        for i, c in enumerate(chunks, start=1):
            source = c.metadata.get("filename", "未知来源")
            parts.append(f"[资料{i}·来源:{source}] {c.text}")
        return "\n\n".join(parts)
