"""
稀疏检索（BM25）测试。

覆盖中文/英文分词、索引新增/删除、相关度排序与按文档删除。
"""

from __future__ import annotations

from app.core.rag.sparse import BM25Index


def test_add_and_count():
    """新增片段应正确计入索引数量。"""
    idx = BM25Index()
    idx.add("c1", "机器学习 与 人工智能", {"document_id": "d1"})
    idx.add("c2", "红烧肉 的做法", {"document_id": "d2"})
    assert idx.count() == 2


def test_search_relevant_first():
    """相关文档应排在检索结果首位。"""
    idx = BM25Index()
    idx.add("c1", "机器学习是人工智能的核心", {"document_id": "d1"})
    idx.add("c2", "红烧肉要先焯水再加糖", {"document_id": "d2"})
    hits = idx.search("机器学习", top_k=5)
    assert hits and hits[0].chunk_id == "c1"
    assert hits[0].score > 0


def test_search_english_term():
    """英文专业术语应能精确命中。"""
    idx = BM25Index()
    idx.add("c1", "Kubernetes 是一个容器编排平台", {"document_id": "d1"})
    idx.add("c2", "Python 是一门编程语言", {"document_id": "d2"})
    hits = idx.search("Kubernetes 编排", top_k=5)
    assert hits and hits[0].chunk_id == "c1"


def test_search_chinese_bigram():
    """中文 bigram 应能区分相近但不同的词。"""
    idx = BM25Index()
    idx.add("c1", "回龙观是北京的一个地区", {"document_id": "d1"})
    idx.add("c2", "这是关于龙和观的讨论", {"document_id": "d2"})
    hits = idx.search("回龙观", top_k=5)
    assert hits and hits[0].chunk_id == "c1"


def test_remove_by_document():
    """按文档删除应移除其全部片段并正确维护词频。"""
    idx = BM25Index()
    idx.add("c1", "内容一 甲乙丙", {"document_id": "d1"})
    idx.add("c2", "内容二 丁戊己", {"document_id": "d2"})
    removed = idx.remove_by_document("d1")
    assert removed == 1
    assert idx.count() == 1
    hits = idx.search("甲乙丙", top_k=5)
    assert all(h.chunk_id != "c1" for h in hits)


def test_empty_index_search():
    """空索引检索应返回空列表。"""
    idx = BM25Index()
    assert idx.search("任意查询", top_k=5) == []
