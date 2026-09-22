"""
RAG 缓存模块。

提供两层低开销缓存，降低重复开销：
1. ``CachedEmbedder``：嵌入器装饰器，缓存「查询文本 → 向量」，
   避免对相同/高频追问重复调用嵌入（尤其远端 API 时，省一次网络往返与计费）。
2. ``RetrievalCache``：检索结果 TTL 缓存，键含向量库版本号，
   任何写入/删除自动失效，保证一致性。

两者均为进程内缓存（cachetools.TTLCache），零外部依赖、微秒级命中。
"""

from __future__ import annotations

import hashlib
import threading
from typing import List, Optional, Tuple

from cachetools import TTLCache

from app.core.rag.embeddings import BaseEmbedder
from app.core.rag.vectorstore import RetrievedChunk
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _hash(text: str) -> str:
    """对缓存键材料做稳定哈希。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class CachedEmbedder(BaseEmbedder):
    """
    嵌入器缓存装饰器：仅缓存 ``embed_query``（文档批量嵌入不做缓存，
    因为摄取通常是一次性操作，缓存收益低且占内存）。

    Args:
        inner: 实际嵌入器。
        ttl: 缓存有效期（秒）。
        maxsize: 最大缓存条数。
    """

    def __init__(self, inner: BaseEmbedder, ttl: int = 300, maxsize: int = 1024) -> None:
        self._inner = inner
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    @property
    def dimension(self) -> int:  # 透传内部嵌入器维度
        return self._inner.dimension

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量文档嵌入不缓存，直接透传。"""
        return self._inner.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        """查询嵌入带 TTL 缓存。"""
        key = _hash(f"{self._inner.__class__.__name__}|{getattr(self._inner, '_model', '')}|{text}")
        with self._lock:
            hit = self._cache.get(key)
        if hit is not None:
            self.hits += 1
            return list(hit)
        vec = self._inner.embed_query(text)
        with self._lock:
            self._cache[key] = vec
        self.misses += 1
        return vec

    def stats(self) -> dict:
        """返回缓存命中统计（供 /api/metrics 观测）。"""
        return {"hits": self.hits, "misses": self.misses, "size": len(self._cache)}


class RetrievalCache:
    """
    检索结果缓存：键 = (查询哈希, 稠密查询哈希, kb, 文档过滤, top_k, 阈值, 库版本, 是否重排)。

    向量库每次写入/删除都会递增 version，缓存键包含版本号 →
    任何内容变更自动使旧缓存项无法命中（TTL 兜底清理）。
    """

    def __init__(self, ttl: int = 120, maxsize: int = 512) -> None:
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _key(
        query: str,
        dense_query: Optional[str],
        kb_id: Optional[str],
        document_id: Optional[str],
        top_k: int,
        min_score: float,
        store_version: int,
        rerank_on: bool,
        mmr_on: bool,
    ) -> Tuple:
        return (
            _hash(query),
            _hash(dense_query) if dense_query else "",
            kb_id or "",
            document_id or "",
            top_k,
            round(min_score, 4),
            store_version,
            rerank_on,
            mmr_on,
        )

    def get(self, *key_parts) -> Optional[List[RetrievedChunk]]:
        """命中返回缓存结果副本（防外部修改污染缓存），未命中返回 None。"""
        key = self._key(*key_parts)
        with self._lock:
            hit = self._cache.get(key)
        if hit is None:
            self.misses += 1
            return None
        self.hits += 1
        return [
            RetrievedChunk(chunk_id=c.chunk_id, text=c.text, score=c.score, metadata=dict(c.metadata))
            for c in hit
        ]

    def set(self, key_parts: Tuple, value: List[RetrievedChunk]) -> None:
        with self._lock:
            self._cache[self._key(*key_parts)] = [
                RetrievedChunk(chunk_id=c.chunk_id, text=c.text, score=c.score, metadata=dict(c.metadata))
                for c in value
            ]

    def stats(self) -> dict:
        return {"hits": self.hits, "misses": self.misses, "size": len(self._cache)}
