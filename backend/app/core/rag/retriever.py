"""
检索器模块。

将「文档摄取（索引构建）」与「语义检索」封装为高层 API，
是 RAG 系统对上层业务暴露的主入口。内部编排：加载 → 分块 → 嵌入 → 入库 / 检索。

v2 升级点：
- 知识库（kb_id）级隔离：多租户场景下各产品只检索自己的语料；
- 检索结果 TTL 缓存（随向量库版本自动失效）；
- 可选 MMR 多样性重排（λ 权衡相关性与重复度），避免上下文被同义片段挤占；
- 可选 HyDE 查询扩展：dense_query 与原始查询分离，稠密路用假设文档嵌入；
- Contextual Retrieval：索引期可为片段注入 LLM 上下文前缀（embed_texts ≠ texts）。
"""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional, Sequence

import numpy as np

from app.core.rag.cache import RetrievalCache
from app.core.rag.embeddings import BaseEmbedder
from app.core.rag.reranker import BaseReranker, NoOpReranker
from app.core.rag.sparse import BM25Index
from app.core.rag.splitter import TextSplitter
from app.core.rag.vectorstore import RetrievedChunk, VectorStore
from app.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_KB = "default"


class Retriever:
    """RAG 检索器：负责索引构建与语义检索（可选两阶段重排序 + MMR）。"""

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
        mmr_enabled: bool = True,
        mmr_lambda: float = 0.7,
        retrieval_cache: Optional[RetrievalCache] = None,
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
            mmr_enabled: 是否启用 MMR（最大边际相关性）多样性重排。
            mmr_lambda: MMR 权衡系数，越大越偏相关性、越小越偏多样性。
            retrieval_cache: 检索结果缓存（None 则不缓存）。
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
        self._mmr_enabled = mmr_enabled
        self._mmr_lambda = mmr_lambda
        self._cache = retrieval_cache

    def set_reranker(self, reranker: BaseReranker, candidate_k: Optional[int] = None) -> None:
        """热替换重排序器（配置变更后由容器调用），可同时更新候选召回数。"""
        self._reranker = reranker or NoOpReranker()
        if candidate_k is not None:
            self._candidate_k = candidate_k

    def set_embedder(self, embedder: BaseEmbedder) -> None:
        """热替换嵌入器（切换嵌入配置后由容器调用）。"""
        self._store.set_embedder(embedder)

    def split_text(self, text: str) -> List:
        """用内置分块器切分文本，返回 Chunk 列表（供摄取前的上下文增强等使用）。"""
        return self._splitter.split(text)

    def index_document(
        self,
        document_id: str,
        filename: str,
        text: str,
        kb_id: str = DEFAULT_KB,
        embed_contexts: Optional[Sequence[str]] = None,
    ) -> int:
        """
        对单个文档构建索引：分块并写入向量库。

        Args:
            document_id: 文档唯一 ID。
            filename: 原始文件名（存入元数据，便于溯源）。
            text: 文档纯文本内容。
            kb_id: 知识库 ID（多租户隔离粒度，写入每条片段元数据）。
            embed_contexts: 可选，每块对应的「上下文前缀」（Contextual Retrieval）。
                提供时嵌入用 ``前缀 + 原文``，展示仍用原文。长度需与分块数一致。

        Returns:
            int: 生成并入库的片段数量。
        """
        chunks = self._splitter.split(text)
        if not chunks:
            logger.warning("文档 %s 分块为空，跳过索引", filename)
            return 0

        if embed_contexts is not None and len(embed_contexts) != len(chunks):
            logger.warning("上下文前缀数量(%d)与分块数(%d)不一致，忽略前缀", len(embed_contexts), len(chunks))
            embed_contexts = None

        chunk_ids: List[str] = []
        texts: List[str] = []
        embed_texts: List[str] = []
        metadatas: List[Dict[str, str]] = []
        for i, chunk in enumerate(chunks):
            chunk_ids.append(f"{document_id}:{chunk.index}:{uuid.uuid4().hex[:8]}")
            texts.append(chunk.text)
            prefix = embed_contexts[i] if embed_contexts else ""
            embed_texts.append(f"{prefix}{chunk.text}" if prefix else chunk.text)
            metadatas.append(
                {
                    "document_id": document_id,
                    "filename": filename,
                    "chunk_index": str(chunk.index),
                    "kb_id": kb_id,
                }
            )

        self._store.add_chunks(chunk_ids, texts, metadatas, embed_texts=embed_texts)
        # 同步更新稀疏索引（混合检索用）；稀疏侧用展示文本（含上下文前缀也注入关键词，
        # 对 BM25 召回同样有益，故用 embed_texts）
        if self._sparse is not None:
            for cid, t, m in zip(chunk_ids, embed_texts, metadatas):
                self._sparse.add(cid, t, m)
        logger.info("文档 %s 索引完成（kb=%s），共 %d 个片段", filename, kb_id, len(chunks))
        return len(chunks)

    def retrieve(
        self,
        query: str,
        top_k: int = 4,
        document_id: str | None = None,
        min_score: float = 0.0,
        kb_id: Optional[str] = None,
        dense_query: Optional[str] = None,
    ) -> List[RetrievedChunk]:
        """
        检索与查询最相关的片段（支持混合检索 + 可选重排序 + MMR）。

        检索策略：
        1. 混合检索（默认）：向量稠密检索 + BM25 稀疏检索 → RRF 倒数排名融合；
        2. 若启用重排序，则在融合后再由 Cross-Encoder 精排；
        3. 若启用 MMR，则在 top_k 内做多样性挑选（λ 权衡）；
        4. 最后按 min_score 过滤噪音。任一路失败都会降级而不阻断主流程。

        Args:
            query: 查询文本（稀疏路与日志用）。
            top_k: 返回条数。
            document_id: 若指定，则仅在该文档范围内检索。
            min_score: 相关性阈值，低于此分数的片段视为噪音被过滤。
            kb_id: 知识库 ID；指定时仅在该知识库范围内检索（多租户隔离）。
            dense_query: 可选的稠密检索专用查询文本（HyDE：假设性回答嵌入），
                缺省与 query 相同。

        Returns:
            List[RetrievedChunk]: 相关片段列表（可能为空）。
        """
        where: Dict[str, str] = {}
        if document_id:
            where["document_id"] = document_id
        if kb_id:
            where["kb_id"] = kb_id
        where_or_none = where or None

        # 1) 缓存命中直接返回（键含库版本号，写入即失效）
        if self._cache is not None:
            key = (
                query, dense_query, kb_id, document_id, top_k, min_score,
                self._store.version, self._reranker.enabled, self._mmr_enabled,
            )
            hit = self._cache.get(*key)
            if hit is not None:
                logger.info("检索缓存命中 '%s'", query[:30])
                return hit
        else:
            key = None

        dense_input = dense_query or query

        # 混合检索：向量 + 稀疏 → RRF 融合
        if self._hybrid and self._sparse is not None:
            candidate_k = max(top_k, self._candidate_k)
            dense = self._store.query(
                dense_input, top_k=candidate_k, where=where_or_none, min_score=0.0
            )
            sparse = self._sparse.search(query, top_k=candidate_k, where=where_or_none)
            fused = self._rrf_fuse(
                dense, sparse, top_k=max(candidate_k, top_k), k=self._rrf_k,
                dense_weight=self._dense_weight, sparse_weight=self._sparse_weight,
            )
            if self._reranker.enabled:
                fused = self._reranker.rerank(query, fused, top_n=max(candidate_k, top_k))
            results = self._apply_mmr(dense_input, fused, top_k)
            results = [c for c in results if c.score >= min_score]
            logger.info(
                "混合检索 '%s'（kb=%s）：向量 %d + 稀疏 %d → 融合 %d（阈值=%.3f）",
                query[:30], kb_id, len(dense), len(sparse), len(results), min_score,
            )
            if key is not None:
                self._cache.set(key, results)
            return results

        # 纯向量检索（未启用混合检索时）：两阶段（召回 + 重排 + MMR）
        if self._reranker.enabled:
            candidate_k = max(top_k, self._candidate_k)
            candidates = self._store.query(
                dense_input, top_k=candidate_k, where=where_or_none, min_score=0.0
            )
            reranked = self._reranker.rerank(query, candidates, top_n=max(candidate_k, top_k))
            results = self._apply_mmr(dense_input, reranked, top_k)
            results = [c for c in results if c.score >= min_score]
            logger.info(
                "两阶段检索 '%s'：召回 %d → 重排后命中 %d（阈值=%.3f）",
                query[:30], len(candidates), len(results), min_score,
            )
            if key is not None:
                self._cache.set(key, results)
            return results

        candidates = self._store.query(
            dense_input, top_k=max(top_k, self._candidate_k) if self._mmr_enabled else top_k,
            where=where_or_none, min_score=0.0,
        )
        results = self._apply_mmr(dense_input, candidates, top_k)
        results = [c for c in results if c.score >= min_score]
        logger.info("检索 '%s' 命中 %d 个片段（阈值=%.3f）", query[:30], len(results), min_score)
        if key is not None:
            self._cache.set(key, results)
        return results

    def _apply_mmr(
        self,
        query: str,
        candidates: List[RetrievedChunk],
        top_k: int,
    ) -> List[RetrievedChunk]:
        """
        MMR（Maximal Marginal Relevance）多样性重排。

        贪心选择：每步选取 ``λ·相关性 − (1−λ)·与已选集合最大相似度`` 最大的候选，
        使结果既相关又彼此差异化，避免 top_k 被同一语义的重复片段挤占。
        失败/无向量时原样返回（零副作用）。

        Args:
            query: 稠密检索使用的查询文本。
            candidates: 候选片段（已按相关性排序）。
            top_k: 返回条数。
        """
        if not self._mmr_enabled or len(candidates) <= 1:
            return candidates[:top_k]
        try:
            ids = [c.chunk_id for c in candidates]
            emb = self._store.get_embeddings(ids)
            if len(emb) < len(candidates):
                return candidates[:top_k]
            query_vec = self._store.get_query_embedding(query)
            cand_mat = np.stack([emb[cid] for cid in ids])
            rel = cand_mat @ query_vec  # 与查询的余弦相关度

            selected: List[int] = []
            remaining = list(range(len(candidates)))
            lam = self._mmr_lambda
            while remaining and len(selected) < top_k:
                if not selected:
                    pick = int(np.argmax(rel[remaining]))
                    pick = remaining[pick]
                else:
                    sel_mat = cand_mat[selected]
                    # 每个候选与已选集合的最大相似度
                    sim_to_sel = cand_mat[remaining] @ sel_mat.T
                    max_sim = sim_to_sel.max(axis=1)
                    mmr = lam * rel[remaining] - (1 - lam) * max_sim
                    pick = remaining[int(np.argmax(mmr))]
                selected.append(pick)
                remaining.remove(pick)
            return [candidates[i] for i in selected]
        except Exception as exc:  # noqa: BLE001 多样性重排失败不阻断检索
            logger.warning("MMR 重排失败，使用原始顺序: %s", exc)
            return candidates[:top_k]

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

    def delete_document(self, document_id: str, kb_id: Optional[str] = None) -> None:
        """删除某文档的全部索引片段；可选限定知识库范围。"""
        self._store.delete_by_document(document_id)
        if self._sparse is not None:
            self._sparse.remove_by_document(document_id)

    def count(self, kb_id: Optional[str] = None) -> int:
        """返回向量库中的片段总数；可选按知识库过滤。"""
        if kb_id:
            return self._store.count(where={"kb_id": kb_id})
        return self._store.count()

    def all_chunks(self, kb_id: Optional[str] = None) -> List[RetrievedChunk]:
        """返回向量库内全部片段（供知识图谱等全量遍历场景）；可选按知识库过滤。"""
        if kb_id:
            return self._store.all_chunks(where={"kb_id": kb_id})
        return self._store.all_chunks()

    def rebuild_sparse_from_store(self) -> int:
        """
        从向量库全量回填稀疏索引（启动时调用）。

        稀疏索引为纯内存结构，重启后为空；回填使混合检索跨重启仍可用。

        Returns:
            int: 回填的片段数。
        """
        if self._sparse is None:
            return 0
        chunks = self._store.all_chunks()
        for c in chunks:
            self._sparse.add(c.chunk_id, c.text, c.metadata)
        if chunks:
            logger.info("稀疏索引已回填 %d 个片段", len(chunks))
        return len(chunks)

    def close(self) -> None:
        """释放底层向量库资源（关闭 SQLite 连接），应用关闭时调用。"""
        try:
            self._store.close()
        except Exception:  # noqa: BLE001
            pass

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
