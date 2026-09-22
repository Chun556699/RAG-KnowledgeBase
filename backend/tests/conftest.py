"""
测试通用夹具（fixtures）。

提供临时的内存/磁盘资源与一个内存版假向量库，
使核心逻辑测试无需外部服务即可运行。
"""

from __future__ import annotations

from typing import Dict, List, Optional

import pytest

from app.core.memory.manager import MemoryManager
from app.core.memory.store import MemoryStore
from app.core.rag.embeddings import MockEmbedder
from app.core.rag.vectorstore import RetrievedChunk


@pytest.fixture
def memory_store(tmp_path) -> MemoryStore:
    """基于临时文件的 SQLite 记忆存储，测试结束自动清理。"""
    store = MemoryStore(str(tmp_path / "test_memory.db"))
    yield store
    store.close()


@pytest.fixture
def memory_manager(memory_store) -> MemoryManager:
    """基于临时存储的记忆管理器。"""
    return MemoryManager(memory_store, max_history_turns=10, ttl_days=30)


class FakeVectorStore:
    """
    内存版假向量库，供 Retriever 单元测试使用。

    使用 MockEmbedder 计算向量，以余弦相似度模拟真实向量库的检索行为，
    实现与真实 VectorStore 一致的方法签名（鸭子类型）。
    """

    def __init__(self) -> None:
        self._embedder = MockEmbedder(dimension=128)
        self._version = 0
        # chunk_id -> (text, vector, metadata)
        self._data: Dict[str, tuple] = {}

    @property
    def version(self) -> int:
        """数据版本号：每次写入递增（与真实向量库语义一致）。"""
        return self._version

    def add_chunks(
        self,
        chunk_ids: List[str],
        texts: List[str],
        metadatas: List[Dict[str, str]],
        embed_texts: Optional[List[str]] = None,
    ) -> None:
        embed_input = embed_texts if embed_texts is not None else texts
        vectors = self._embedder.embed_documents(embed_input)
        for cid, text, vec, meta in zip(chunk_ids, texts, vectors, metadatas):
            self._data[cid] = (text, vec, meta)
        self._version += 1

    def query(
        self,
        query: str,
        top_k: int = 4,
        where: Optional[Dict[str, str]] = None,
        min_score: float = 0.0,
    ) -> List[RetrievedChunk]:
        qv = self._embedder.embed_query(query)
        scored = []
        for cid, (text, vec, meta) in self._data.items():
            if where and any(meta.get(k) != v for k, v in where.items()):
                continue
            score = sum(a * b for a, b in zip(qv, vec))
            scored.append(RetrievedChunk(chunk_id=cid, text=text, score=score, metadata=meta))
        scored.sort(key=lambda c: c.score, reverse=True)
        return [c for c in scored[:top_k] if c.score >= min_score]

    def delete_by_document(self, document_id: str) -> None:
        self._data = {
            cid: v
            for cid, v in self._data.items()
            if v[2].get("document_id") != document_id
        }
        self._version += 1

    def count(self, where: Optional[Dict[str, str]] = None) -> int:
        if not where:
            return len(self._data)
        return sum(
            1
            for _, (_, _, meta) in self._data.items()
            if all(meta.get(k) == v for k, v in where.items())
        )

    def all_chunks(self, where: Optional[Dict[str, str]] = None) -> List[RetrievedChunk]:
        out = []
        for cid, (text, vec, meta) in self._data.items():
            if where and any(meta.get(k) != v for k, v in where.items()):
                continue
            out.append(RetrievedChunk(chunk_id=cid, text=text, score=1.0, metadata=meta))
        return out

    def get_embeddings(self, chunk_ids: List[str]) -> List[Optional[List[float]]]:
        return [self._data[cid][1] if cid in self._data else None for cid in chunk_ids]

    def get_query_embedding(self, text: str) -> List[float]:
        return self._embedder.embed_query(text)

    def close(self) -> None:
        pass


@pytest.fixture
def fake_vector_store() -> FakeVectorStore:
    """假向量库实例。"""
    return FakeVectorStore()
