"""
RAG 检索器测试。

使用不依赖 ChromaDB 的 FakeVectorStore（见 conftest），
验证索引构建、语义检索、按文档删除、上下文拼接等编排逻辑。
"""

from __future__ import annotations

from app.core.rag.retriever import Retriever
from app.core.rag.sparse import BM25Index, SparseHit
from app.core.rag.splitter import TextSplitter
from app.core.rag.vectorstore import RetrievedChunk


def _build_retriever(store):
    """用假向量库与小分块器构造检索器。"""
    return Retriever(store, TextSplitter(chunk_size=60, chunk_overlap=10))


def test_index_document_returns_chunk_count(fake_vector_store):
    """索引文档应返回入库片段数，并可被 count 统计。"""
    retriever = _build_retriever(fake_vector_store)
    text = "。".join(f"这是关于机器学习的第{i}段内容" for i in range(20))
    count = retriever.index_document("doc1", "ml.txt", text)
    assert count > 0
    assert retriever.count() == count


def test_retrieve_returns_relevant_chunks(fake_vector_store):
    """检索应返回与查询语义最相关的片段（相关文档排在最前）。"""
    retriever = _build_retriever(fake_vector_store)
    retriever.index_document("d1", "ml.txt", "机器学习 是 人工智能 的核心分支，涉及模型训练。")
    retriever.index_document("d2", "cook.txt", "红烧肉 的做法：先焯水，再加冰糖炒色。")

    results = retriever.retrieve("人工智能 与 机器学习", top_k=2)
    assert len(results) >= 1
    # 最相关的应来自机器学习文档
    assert results[0].metadata["filename"] == "ml.txt"


def test_retrieve_scoped_to_document(fake_vector_store):
    """指定 document_id 时应只在该文档范围内检索。"""
    retriever = _build_retriever(fake_vector_store)
    retriever.index_document("d1", "a.txt", "苹果 香蕉 橙子 水果")
    retriever.index_document("d2", "b.txt", "汽车 火车 飞机 交通")

    results = retriever.retrieve("水果", top_k=5, document_id="d2")
    # 限定在 d2，命中的必然都属于 d2
    assert all(r.metadata["document_id"] == "d2" for r in results)


def test_delete_document(fake_vector_store):
    """删除文档应移除其全部片段。"""
    retriever = _build_retriever(fake_vector_store)
    retriever.index_document("d1", "a.txt", "内容 A 一二三四五六七八九十")
    retriever.index_document("d2", "b.txt", "内容 B 一二三四五六七八九十")
    total = retriever.count()

    retriever.delete_document("d1")
    assert retriever.count() < total
    remaining = retriever.retrieve("内容", top_k=10)
    assert all(r.metadata["document_id"] != "d1" for r in remaining)


def test_build_context_formats_sources(fake_vector_store):
    """build_context 应生成带来源标注的上下文文本。"""
    retriever = _build_retriever(fake_vector_store)
    retriever.index_document("d1", "guide.txt", "检索增强生成结合了检索与大模型。")
    chunks = retriever.retrieve("检索增强", top_k=1)
    context = Retriever.build_context(chunks)
    assert "来源:guide.txt" in context


def test_build_context_empty():
    """空片段列表应返回空字符串。"""
    assert Retriever.build_context([]) == ""


# ---------------- 混合检索（向量 + 稀疏 + RRF） ----------------
def _build_hybrid_retriever(store):
    """用假向量库 + 真实 BM25 稀疏索引构造混合检索器。"""
    return Retriever(
        store,
        TextSplitter(chunk_size=60, chunk_overlap=10),
        sparse_index=BM25Index(),
        hybrid_enabled=True,
    )


def test_hybrid_retrieve_syncs_sparse_index(fake_vector_store):
    """混合检索器应同步维护稀疏索引：索引时新增，删除时移除。"""
    retriever = _build_hybrid_retriever(fake_vector_store)
    count = retriever.index_document("d1", "a.txt", "机器学习 是 人工智能 的 核心 分支")
    assert retriever._sparse.count() == count

    results = retriever.retrieve("机器学习", top_k=3)
    assert len(results) >= 1

    retriever.delete_document("d1")
    assert retriever._sparse.count() == 0


def test_hybrid_retrieve_scoped_to_document(fake_vector_store):
    """混合检索限定 document_id 时，稀疏命中也应被过滤。"""
    retriever = _build_hybrid_retriever(fake_vector_store)
    retriever.index_document("d1", "a.txt", "苹果 香蕉 橙子 水果")
    retriever.index_document("d2", "b.txt", "汽车 火车 飞机 交通")

    results = retriever.retrieve("水果", top_k=5, document_id="d2")
    assert all(r.metadata["document_id"] == "d2" for r in results)


def test_rrf_fuse_boosts_chunk_in_both_lists():
    """两路都命中的片段经 RRF 融合后应排名第一，且得分为 1.0。"""
    dense = [
        RetrievedChunk(chunk_id="both", text="t", score=0.9, metadata={}),
        RetrievedChunk(chunk_id="dense_only", text="t", score=0.8, metadata={}),
    ]
    sparse = [
        SparseHit(chunk_id="both", text="t", score=1.0, metadata={}),
        SparseHit(chunk_id="sparse_only", text="t", score=0.5, metadata={}),
    ]
    fused = Retriever._rrf_fuse(dense, sparse, top_k=3, k=60)
    assert fused[0].chunk_id == "both"
    assert fused[0].score == 1.0
    assert len(fused) == 3
