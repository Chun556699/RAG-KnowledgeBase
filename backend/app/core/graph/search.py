"""
图谱检索器（GraphRAG 检索）。

将「知识图谱」从单纯的可视化能力升级为「检索增强」能力：查询时先在图谱中
定位相关实体，再沿关系边扩展邻居（1 跳），返回相关的「实体-关系-实体」三元组。
这些三元组作为额外的图谱上下文与向量/稀疏检索的片段一并注入提示词，
使系统具备 LightRAG 式的「图增强检索」能力，能捕捉间接关联与多跳语义。

与向量/稀疏检索互补：
- 向量/稀疏检索：找「字面/语义相近」的文档片段；
- 图谱检索：找「实体关系上相关」的知识关联（如 A 依赖 B、B 属于 C）。
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from app.core.graph.builder import KnowledgeGraph
from app.utils.logger import get_logger

logger = get_logger(__name__)


class GraphSearcher:
    """
    图谱检索器：从知识图谱中检索与查询相关的实体与关系三元组。

    通过 ``graph_provider`` 回调惰性获取当前图谱（图谱可能在运行期被重建），
    从而始终基于最新图谱检索，且无需在每次构建后重建本检索器。
    """

    def __init__(self, graph_provider: Callable[[], KnowledgeGraph]) -> None:
        """
        Args:
            graph_provider: 返回当前知识图谱的回调（通常为 GraphService.get_graph）。
        """
        self._graph_provider = graph_provider

    def search(
        self,
        query: str,
        max_hops: int = 1,
        max_triples: int = 20,
    ) -> List[Dict[str, str]]:
        """
        检索与查询相关的实体关系三元组。

        流程：实体匹配 → 邻居扩展（沿边）→ 收集三元组 → 去重截断。
        图谱为空或未命中任何实体时返回空列表。

        Args:
            query: 查询文本。
            max_hops: 邻居扩展的最大跳数（1 = 仅直接邻居）。
            max_triples: 返回三元组的上限。

        Returns:
            List[Dict[str, str]]: 三元组列表，每项含 source/relation/target。
        """
        graph = self._graph_provider()
        if graph is None or not graph.nodes:
            return []

        node_by_id = {n.id: n for n in graph.nodes}

        # 1) 实体匹配：查询文本包含实体名（或实体名包含查询，处理中文子串）
        q_lower = query.lower()
        matched: set[str] = set()
        for n in graph.nodes:
            label = n.label.strip()
            if not label:
                continue
            label_lower = label.lower()
            if label_lower in q_lower or (len(label_lower) >= 2 and label_lower in q_lower):
                matched.add(n.id)
        if not matched:
            return []

        # 2) 邻居扩展：沿边将直接邻居（可多跳）纳入相关实体集合
        expanded = set(matched)
        for _ in range(max_hops):
            frontier: set[str] = set()
            for e in graph.edges:
                if e.source in expanded and e.target not in expanded:
                    frontier.add(e.target)
                elif e.target in expanded and e.source not in expanded:
                    frontier.add(e.source)
            if not frontier:
                break
            expanded |= frontier

        # 3) 收集相关三元组（源或目标在扩展后的实体集合中），并去重
        triples: List[Dict[str, str]] = []
        seen: set[tuple] = set()
        for e in graph.edges:
            if e.source not in expanded and e.target not in expanded:
                continue
            s = node_by_id.get(e.source)
            t = node_by_id.get(e.target)
            source = s.label if s else e.source
            target = t.label if t else e.target
            key = (source, e.relation, target)
            if key in seen:
                continue
            seen.add(key)
            triples.append({"source": source, "relation": e.relation, "target": target})
            if len(triples) >= max_triples:
                break

        logger.info(
            "图谱检索 '%s'：命中实体 %d → 扩展 %d → 三元组 %d",
            query[:30], len(matched), len(expanded), len(triples),
        )
        return triples

    @staticmethod
    def build_context(triples: List[Dict[str, str]]) -> str:
        """
        将三元组拼接为可注入提示词的图谱上下文文本。

        Args:
            triples: 三元组列表（source/relation/target）。

        Returns:
            str: 图谱上下文文本；空列表返回空字符串。
        """
        if not triples:
            return ""
        lines = [
            f"[图谱关系{i}] {t['source']} -{t['relation']}-> {t['target']}"
            for i, t in enumerate(triples, start=1)
        ]
        return "\n".join(lines)
