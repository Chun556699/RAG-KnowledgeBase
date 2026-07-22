"""
向量存储模块（本地轻量向量库）。

使用 numpy 实现的纯 Python 本地持久化向量库，替代 ChromaDB：
- 零外部服务依赖，离线可运行，Docker 友好；
- 向量以 numpy 数组内存索引，文本/元数据一并持久化到单个磁盘文件；
- 检索采用余弦相似度（向量已由 Embedder 归一化，等价于点积）。

关键设计：**将嵌入计算交给我们自己的 Embedder**，本库仅负责向量索引、
持久化与相似度检索，从而与嵌入提供商解耦。
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from app.core.rag.embeddings import BaseEmbedder
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RetrievedChunk:
    """
    检索命中的文档片段。

    Attributes:
        chunk_id: 片段唯一 ID。
        text: 片段文本。
        score: 相似度分数（0~1，越大越相关）。
        metadata: 附加元数据（文档 ID、文件名、块序号等）。
    """

    chunk_id: str
    text: str
    score: float
    metadata: Dict[str, str]


class VectorStore:
    """
    基于 numpy 的本地持久化向量存储。

    数据以三份平行列表（ids/texts/metadatas）加一个二维向量矩阵（vectors）
    组织，整体 pickle 到 `persist_path`。所有写操作后立即落盘，保证重启不丢失。
    """

    def __init__(self, persist_path: str, embedder: BaseEmbedder) -> None:
        """
        Args:
            persist_path: 向量库持久化文件路径（单文件，如 ./data/vectorstore.json）。
            embedder: 嵌入器实例（负责计算向量）。
        """
        self._embedder = embedder
        self._path = Path(persist_path)
        self._lock = threading.RLock()

        # 平行结构：ids[i] 对应 texts[i] / metadatas[i] / vectors[i]
        self._ids: List[str] = []
        self._texts: List[str] = []
        self._metadatas: List[Dict[str, str]] = []
        # 向量矩阵：shape=(N, dim)，N 为片段数
        self._vectors: np.ndarray = np.empty((0, 0), dtype=np.float32)

        self._load()
        logger.info("向量库就绪：path=%s，现有条目=%d", self._path, len(self._ids))

    def set_embedder(self, embedder: BaseEmbedder) -> None:
        """
        热替换嵌入器（切换嵌入提供商/模型后调用）。

        注意：若新嵌入的向量维度与库内已有向量不一致，query 时的维度守卫会
        返回空结果并告警，需重新上传文档重建索引。
        """
        with self._lock:
            self._embedder = embedder
        logger.info("向量库嵌入器已更新（如维度变化需重建索引）")

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------
    def _load(self) -> None:
        """
        从磁盘加载已有数据（文件不存在时视为空库）。

        采用 JSON 明文格式持久化，避免 pickle 反序列化带来的任意代码执行风险，
        且便于跨版本迁移与人工排查。
        """
        if not self._path.exists():
            return
        try:
            with self._path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            self._ids = data.get("ids", [])
            self._texts = data.get("texts", [])
            self._metadatas = data.get("metadatas", [])
            vectors = data.get("vectors")
            self._vectors = (
                np.asarray(vectors, dtype=np.float32)
                if vectors
                else np.empty((0, 0), dtype=np.float32)
            )
        except Exception as exc:  # noqa: BLE001  持久化损坏时不阻塞启动
            logger.error("加载向量库失败，将以空库启动: %s", exc)
            self._ids, self._texts, self._metadatas = [], [], []
            self._vectors = np.empty((0, 0), dtype=np.float32)

    def _persist(self) -> None:
        """将当前数据落盘（原子写：先写临时文件再替换）。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "ids": self._ids,
                    "texts": self._texts,
                    "metadatas": self._metadatas,
                    # numpy 数组转为嵌套列表以便 JSON 序列化
                    "vectors": self._vectors.tolist() if self._vectors.size else [],
                },
                f,
                ensure_ascii=False,
            )
        tmp.replace(self._path)

    @staticmethod
    def _normalize(matrix: np.ndarray) -> np.ndarray:
        """对每行做 L2 归一化，使点积等价于余弦相似度。"""
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return matrix / norms

    # ------------------------------------------------------------------
    # 写入 / 删除
    # ------------------------------------------------------------------
    def add_chunks(
        self,
        chunk_ids: List[str],
        texts: List[str],
        metadatas: List[Dict[str, str]],
    ) -> None:
        """
        写入文档片段（含向量）。

        Args:
            chunk_ids: 片段 ID 列表。
            texts: 片段文本列表。
            metadatas: 片段元数据列表。三者长度需一致。
        """
        if not texts:
            return
        embeddings = self._embedder.embed_documents(texts)
        new_vectors = np.asarray(embeddings, dtype=np.float32)

        with self._lock:
            self._ids.extend(chunk_ids)
            self._texts.extend(texts)
            self._metadatas.extend(metadatas)
            if self._vectors.size == 0:
                self._vectors = new_vectors
            else:
                self._vectors = np.vstack([self._vectors, new_vectors])
            self._persist()
        logger.info("写入 %d 个片段到向量库", len(texts))

    def query(
        self,
        query_text: str,
        top_k: int = 4,
        where: Optional[Dict[str, str]] = None,
        min_score: float = 0.0,
    ) -> List[RetrievedChunk]:
        """
        语义检索最相关的片段。

        Args:
            query_text: 查询文本。
            top_k: 返回条数。
            where: 元数据过滤条件（如按 document_id 过滤）。
            min_score: 相关性阈值，低于该余弦相似度的片段被丢弃。

        Returns:
            List[RetrievedChunk]: 按相关度降序排列、且不低于阈值的片段列表。
        """
        with self._lock:
            if not self._ids:
                return []

            query_vec = np.asarray(self._embedder.embed_query(query_text), dtype=np.float32)
            # 维度守卫：切换嵌入器后若未重建索引，查询向量与库内向量维度不一致，
            # 此时不强行计算（会报错），而是告警并返回空，提示需重建索引。
            if query_vec.shape[0] != self._vectors.shape[1]:
                logger.warning(
                    "查询向量维度(%d)与库内维度(%d)不一致，请切换嵌入后重新上传文档重建索引",
                    query_vec.shape[0],
                    self._vectors.shape[1],
                )
                return []
            # 归一化后点积即余弦相似度
            norm = np.linalg.norm(query_vec)
            if norm > 0:
                query_vec = query_vec / norm
            matrix = self._normalize(self._vectors)
            scores = matrix @ query_vec  # shape=(N,)

            # 先按元数据过滤，得到候选下标
            candidate_idx = [
                i
                for i in range(len(self._ids))
                if not where
                or all(self._metadatas[i].get(k) == v for k, v in where.items())
            ]
            if not candidate_idx:
                return []

            # 在候选中按分数降序取 top_k，并按阈值过滤噪音
            candidate_idx.sort(key=lambda i: float(scores[i]), reverse=True)
            selected = candidate_idx[: min(top_k, len(candidate_idx))]

            return [
                RetrievedChunk(
                    chunk_id=self._ids[i],
                    text=self._texts[i],
                    score=round(float(scores[i]), 4),
                    metadata=self._metadatas[i] or {},
                )
                for i in selected
                if float(scores[i]) >= min_score
            ]

    def delete_by_document(self, document_id: str) -> None:
        """删除某文档的所有片段（用于文档删除场景）。"""
        with self._lock:
            keep = [
                i
                for i in range(len(self._ids))
                if self._metadatas[i].get("document_id") != document_id
            ]
            if len(keep) == len(self._ids):
                return  # 无匹配，跳过
            self._ids = [self._ids[i] for i in keep]
            self._texts = [self._texts[i] for i in keep]
            self._metadatas = [self._metadatas[i] for i in keep]
            self._vectors = (
                self._vectors[keep] if keep else np.empty((0, 0), dtype=np.float32)
            )
            self._persist()
        logger.info("已删除文档 %s 的全部片段", document_id)

    def count(self) -> int:
        """返回当前库中的片段总数。"""
        return len(self._ids)

    def all_chunks(self) -> List[RetrievedChunk]:
        """
        返回库内全部片段（不含相似度计算，score 恒为 0）。

        供知识图谱构建等需要遍历全量语料的场景使用。
        """
        with self._lock:
            return [
                RetrievedChunk(
                    chunk_id=self._ids[i],
                    text=self._texts[i],
                    score=0.0,
                    metadata=self._metadatas[i] or {},
                )
                for i in range(len(self._ids))
            ]
