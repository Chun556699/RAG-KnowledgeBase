"""
本地向量库（numpy 实现）测试。

验证 VectorStore 的写入、语义检索、元数据过滤、按文档删除与磁盘持久化。
使用离线 MockEmbedder，无需任何外部服务。
"""

from __future__ import annotations

from app.core.rag.embeddings import MockEmbedder
from app.core.rag.vectorstore import VectorStore


def _make_store(tmp_path) -> VectorStore:
    """构造基于临时文件的向量库实例。"""
    return VectorStore(
        persist_path=str(tmp_path / "vectorstore.json"),
        embedder=MockEmbedder(dimension=128),
    )


def test_add_and_count(tmp_path):
    """写入片段后 count 应正确反映数量。"""
    store = _make_store(tmp_path)
    store.add_chunks(
        ["c1", "c2"],
        ["人工智能与机器学习", "今天天气很好"],
        [{"document_id": "d1"}, {"document_id": "d1"}],
    )
    assert store.count() == 2


def test_query_returns_relevant_first(tmp_path):
    """语义检索应将相关度更高的片段排在前面。"""
    store = _make_store(tmp_path)
    store.add_chunks(
        ["c1", "c2"],
        ["机器学习是人工智能的分支", "今天天气非常好"],
        [{"document_id": "d1"}, {"document_id": "d2"}],
    )
    results = store.query("人工智能 机器学习", top_k=2)
    assert len(results) == 2
    assert results[0].text == "机器学习是人工智能的分支"
    assert results[0].score >= results[1].score


def test_query_metadata_filter(tmp_path):
    """where 过滤应仅返回匹配元数据的片段。"""
    store = _make_store(tmp_path)
    store.add_chunks(
        ["c1", "c2"],
        ["向量检索技术", "向量检索技术"],
        [{"document_id": "d1"}, {"document_id": "d2"}],
    )
    results = store.query("向量检索", top_k=5, where={"document_id": "d2"})
    assert len(results) == 1
    assert results[0].metadata["document_id"] == "d2"


def test_delete_by_document(tmp_path):
    """按文档删除应移除该文档的全部片段。"""
    store = _make_store(tmp_path)
    store.add_chunks(
        ["c1", "c2", "c3"],
        ["a", "b", "c"],
        [{"document_id": "d1"}, {"document_id": "d1"}, {"document_id": "d2"}],
    )
    store.delete_by_document("d1")
    assert store.count() == 1


def test_persistence_across_instances(tmp_path):
    """数据应持久化到磁盘，重新加载后仍可检索。"""
    path = tmp_path / "vectorstore.json"
    store = VectorStore(persist_path=str(path), embedder=MockEmbedder(dimension=128))
    store.add_chunks(["c1"], ["检索增强生成 RAG"], [{"document_id": "d1"}])

    # 新实例从磁盘加载
    reloaded = VectorStore(persist_path=str(path), embedder=MockEmbedder(dimension=128))
    assert reloaded.count() == 1
    results = reloaded.query("RAG", top_k=1)
    assert len(results) == 1


def test_empty_store_query(tmp_path):
    """空库检索应返回空列表而非报错。"""
    store = _make_store(tmp_path)
    assert store.query("任意查询") == []
