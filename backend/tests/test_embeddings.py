"""
嵌入模块测试。

验证 MockEmbedder 的确定性、归一化性质，以及"共享词汇越多相似度越高"的语义特性。
"""

from __future__ import annotations

import math

from app.core.rag.embeddings import MockEmbedder, create_embedder


def _cosine(a, b):
    """计算两向量余弦相似度（向量已归一化时等价于点积）。"""
    return sum(x * y for x, y in zip(a, b))


def test_embedding_dimension():
    """嵌入向量维度应与配置一致。"""
    embedder = MockEmbedder(dimension=256)
    vec = embedder.embed_query("你好世界")
    assert len(vec) == 256


def test_embedding_deterministic():
    """相同文本应产生完全相同的向量（确定性）。"""
    embedder = MockEmbedder()
    v1 = embedder.embed_query("检索增强生成 RAG")
    v2 = embedder.embed_query("检索增强生成 RAG")
    assert v1 == v2


def test_embedding_normalized():
    """非空文本的向量应为 L2 归一化（模长约为 1）。"""
    embedder = MockEmbedder()
    vec = embedder.embed_query("向量数据库")
    norm = math.sqrt(sum(v * v for v in vec))
    assert abs(norm - 1.0) < 1e-6


def test_semantic_similarity_ordering():
    """共享词汇更多的文本，余弦相似度应更高。"""
    embedder = MockEmbedder()
    query = embedder.embed_query("人工智能 与 机器学习")
    related = embedder.embed_query("机器学习 是 人工智能 的分支")
    unrelated = embedder.embed_query("今天 的 天气 非常 好")
    assert _cosine(query, related) > _cosine(query, unrelated)


def test_empty_text_zero_vector():
    """空文本应返回全零向量（无法归一化）。"""
    embedder = MockEmbedder(dimension=64)
    vec = embedder.embed_query("")
    assert vec == [0.0] * 64


def test_factory_creates_mock():
    """工厂应能按名创建 Mock 嵌入器。"""
    embedder = create_embedder("mock", dimension=100)
    assert isinstance(embedder, MockEmbedder)
    assert embedder.dimension == 100
