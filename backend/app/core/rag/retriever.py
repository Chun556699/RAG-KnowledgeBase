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
    ) -> None:
        """
        Args:
            vector_store: 向量存储实例。
            splitter: 文本分块器实例。
            reranker: 重排序器，为 None 时不启用（等价于 NoOp）。
            candidate_k: 启用重排序时，第一阶段向量召回的候选片段数。
        """
        self._store = vector_store
        self._splitter = splitter
        self._reranker: BaseReranker = reranker or NoOpReranker()
        self._candidate_k = candidate_k

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
        语义检索与查询最相关的片段。

        若启用了重排序，则走两阶段：先从向量库召回 candidate_k 条候选（不过滤阈值），
        再由重排序模型精排至 top_k，最后按 min_score 过滤。重排序失败会自动降级。

        Args:
            query: 查询文本。
            top_k: 返回条数。
            document_id: 若指定，则仅在该文档范围内检索。
            min_score: 相关性阈值，低于此分数的片段视为噪音被过滤。

        Returns:
            List[RetrievedChunk]: 相关片段列表（可能为空）。
        """
        where = {"document_id": document_id} if document_id else None

        # 两阶段：启用重排序时先宽召回再精排
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

    def delete_document(self, document_id: str) -> None:
        """删除某文档的全部索引片段。"""
        self._store.delete_by_document(document_id)

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
