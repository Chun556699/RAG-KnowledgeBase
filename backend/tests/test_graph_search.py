"""
图谱检索器（GraphRAG）测试。

覆盖实体匹配、邻居扩展、无命中与空图谱、上下文拼接。
"""

from __future__ import annotations

from app.core.graph.builder import GraphEdge, GraphNode, KnowledgeGraph
from app.core.graph.search import GraphSearcher


def _make_graph() -> KnowledgeGraph:
    """构造一个包含跨领域边的小型知识图谱。"""
    return KnowledgeGraph(
        nodes=[
            GraphNode(id="ml", label="机器学习", weight=3),
            GraphNode(id="ai", label="人工智能", weight=2),
            GraphNode(id="nn", label="神经网络", weight=2),
            GraphNode(id="cook", label="烹饪", weight=1),
        ],
        edges=[
            GraphEdge(source="ml", target="ai", relation="属于", weight=2),
            GraphEdge(source="ml", target="nn", relation="依赖", weight=1),
            GraphEdge(source="cook", target="ml", relation="无关联", weight=1),
        ],
    )


def test_search_matches_entity():
    """查询命中实体时应返回相关三元组。"""
    searcher = GraphSearcher(lambda: _make_graph())
    triples = searcher.search("机器学习是什么？")
    assert len(triples) >= 2
    labels = {t["source"] for t in triples} | {t["target"] for t in triples}
    assert "机器学习" in labels


def test_search_expands_neighbors():
    """邻居扩展应返回命中实体及其直接邻居的关系边。"""
    searcher = GraphSearcher(lambda: _make_graph())
    triples = searcher.search("机器学习", max_hops=1)
    relations = {(t["source"], t["relation"], t["target"]) for t in triples}
    assert ("机器学习", "属于", "人工智能") in relations
    assert ("机器学习", "依赖", "神经网络") in relations
    # 跨领域边（烹饪-机器学习）也因邻居扩展被包含
    assert any("烹饪" in r for r in relations)


def test_search_no_match_returns_empty():
    """查询未命中任何实体时应返回空列表。"""
    searcher = GraphSearcher(lambda: _make_graph())
    assert searcher.search("量子计算") == []


def test_search_empty_graph():
    """空图谱检索应返回空列表。"""
    searcher = GraphSearcher(lambda: KnowledgeGraph())
    assert searcher.search("机器学习") == []


def test_build_context_formats_triples():
    """build_context 应生成带编号的图谱关系文本。"""
    triples = [{"source": "A", "relation": "属于", "target": "B"}]
    ctx = GraphSearcher.build_context(triples)
    assert "图谱关系1" in ctx
    assert "A" in ctx and "属于" in ctx and "B" in ctx
    assert GraphSearcher.build_context([]) == ""
