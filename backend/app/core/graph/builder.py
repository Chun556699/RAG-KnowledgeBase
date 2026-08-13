"""
知识图谱构建器。

从向量库中的全量文档片段出发，调用 LLM 抽取「实体-关系-实体」三元组，
聚合去重为节点与边，并持久化到单个 JSON 文件。核心流程：

    全量片段 → 采样限流 → 并发 LLM 抽取三元组 → 聚合去重 → 持久化

设计要点：
- 实体归一化（去空白、转小写）作为节点 id，label 取首次出现的原文，
  从而合并同名不同写法的实体；node.weight 记录关联度（出现频次）；
- 同一 (source, relation, target) 的多次出现合并为一条边并累加权重；
- 用 asyncio.Semaphore 限制 LLM 并发；单个片段抽取失败不阻断整体构建。
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.core.llm.base import GenerationConfig, Message, Role
from app.core.llm.factory import LLMFactory
from app.core.llm.prompt import get_template
from app.core.rag.retriever import Retriever
from app.config import Settings
from app.utils.logger import get_logger
from app.utils.parsing import extract_json

logger = get_logger(__name__)


@dataclass
class GraphNode:
    """图谱节点（实体）。"""

    id: str
    label: str
    weight: int = 1


@dataclass
class GraphEdge:
    """图谱边（实体间关系）。"""

    source: str
    target: str
    relation: str
    weight: int = 1


@dataclass
class KnowledgeGraph:
    """图谱聚合结果与构建时间。"""

    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)
    built_at: Optional[float] = None


class KnowledgeGraphBuilder:
    """知识图谱构建器：负责 LLM 抽取、聚合与持久化。"""

    def __init__(
        self,
        llm_factory: LLMFactory,
        retriever: Retriever,
        settings: Settings,
    ) -> None:
        self._llm_factory = llm_factory
        self._retriever = retriever
        self._settings = settings
        self._path = Path(settings.graph_store_path)

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------
    def load(self) -> KnowledgeGraph:
        """从磁盘加载已构建的图谱（文件不存在或损坏时返回空图谱）。"""
        if not self._path.exists():
            return KnowledgeGraph()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            nodes = [
                GraphNode(
                    id=str(n["id"]),
                    label=str(n.get("label", n["id"])),
                    weight=int(n.get("weight", 1)),
                )
                for n in data.get("nodes", [])
            ]
            edges = [
                GraphEdge(
                    source=str(e["source"]),
                    target=str(e["target"]),
                    relation=str(e.get("relation", "")),
                    weight=int(e.get("weight", 1)),
                )
                for e in data.get("edges", [])
            ]
            return KnowledgeGraph(
                nodes=nodes, edges=edges, built_at=data.get("built_at")
            )
        except (OSError, ValueError, KeyError) as exc:
            logger.warning("加载知识图谱失败，将以空图谱返回: %s", exc)
            return KnowledgeGraph()

    def _persist(self, graph: KnowledgeGraph) -> None:
        """将图谱数据落盘（原子写：先写临时文件再替换）。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        payload = {
            "nodes": [
                {"id": n.id, "label": n.label, "weight": n.weight}
                for n in graph.nodes
            ],
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "relation": e.relation,
                    "weight": e.weight,
                }
                for e in graph.edges
            ],
            "built_at": graph.built_at,
        }
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        tmp.replace(self._path)

    # ------------------------------------------------------------------
    # 构建
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize(entity: str) -> str:
        """实体归一化：去首尾空白并转小写，作为合并同名实体的键。"""
        return entity.strip().lower()

    def _select_chunks(self, max_chunks: int) -> List[str]:
        """
        从全量片段中按文档 round-robin 采样，兼顾多文档覆盖度。

        Args:
            max_chunks: 采样上限。

        Returns:
            List[str]: 选中的片段文本列表。
        """
        chunks = self._retriever.all_chunks()
        if not chunks:
            return []

        # 按 document_id 分组，保持各文档内原有顺序
        grouped: Dict[str, List[str]] = {}
        for c in chunks:
            doc_id = c.metadata.get("document_id", "_")
            grouped.setdefault(doc_id, []).append(c.text)

        # round-robin：轮流从每个文档取一个片段，直至达到上限
        selected: List[str] = []
        buckets = list(grouped.values())
        idx = 0
        while len(selected) < max_chunks and any(idx < len(b) for b in buckets):
            for b in buckets:
                if idx < len(b):
                    selected.append(b[idx])
                    if len(selected) >= max_chunks:
                        break
            idx += 1
        return selected

    async def _extract_one(
        self, llm, sem: asyncio.Semaphore, text: str
    ) -> List[Tuple[str, str, str]]:
        """
        对单个片段抽取三元组。失败或无结果时返回空列表，不抛出。

        Returns:
            List[Tuple[str, str, str]]: (source, relation, target) 列表。
        """
        prompt = get_template("graph_extract").render(text=text)
        async with sem:
            try:
                resp = await llm.generate(
                    [Message(Role.USER, prompt)],
                    GenerationConfig(temperature=0.0, max_tokens=512),
                )
            except Exception as exc:  # noqa: BLE001  单片段失败不阻断整体
                logger.warning("片段实体抽取失败，跳过: %s", exc)
                return []

        data = extract_json(resp.content or "")
        if not isinstance(data, list):
            return []
        triples: List[Tuple[str, str, str]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source", "")).strip()
            relation = str(item.get("relation", "")).strip()
            target = str(item.get("target", "")).strip()
            if source and target and source != target:
                triples.append((source, relation or "相关", target))
        return triples

    @staticmethod
    def _aggregate(triples: List[Tuple[str, str, str]]) -> KnowledgeGraph:
        """将三元组聚合为去重后的节点与边。"""
        nodes: Dict[str, GraphNode] = {}
        edges: Dict[Tuple[str, str, str], GraphEdge] = {}

        def touch(entity: str) -> str:
            key = KnowledgeGraphBuilder._normalize(entity)
            if key in nodes:
                nodes[key].weight += 1
            else:
                nodes[key] = GraphNode(id=key, label=entity, weight=1)
            return key

        for source, relation, target in triples:
            s_key = touch(source)
            t_key = touch(target)
            edge_key = (s_key, t_key, relation)
            if edge_key in edges:
                edges[edge_key].weight += 1
            else:
                edges[edge_key] = GraphEdge(
                    source=s_key, target=t_key, relation=relation, weight=1
                )

        return KnowledgeGraph(
            nodes=list(nodes.values()),
            edges=list(edges.values()),
            built_at=time.time(),
        )

    async def build(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        max_chunks: Optional[int] = None,
    ) -> KnowledgeGraph:
        """
        构建知识图谱：采样片段 → 并发 LLM 抽取 → 聚合 → 持久化。

        Args:
            provider: LLM 提供商，缺省用配置默认值。
            model: 模型名，缺省用提供商默认模型。
            max_chunks: 本次最多参与抽取的片段数，缺省用配置值。

        Returns:
            KnowledgeGraph: 构建完成的图谱（已落盘）。
        """
        limit = max_chunks or self._settings.graph_max_chunks
        texts = self._select_chunks(limit)
        if not texts:
            logger.info("知识库为空，构建空图谱")
            graph = KnowledgeGraph(built_at=time.time())
            self._persist(graph)
            return graph

        provider_name = provider or self._llm_factory.default_provider_name()
        llm = self._llm_factory.get_provider(provider_name, model)
        sem = asyncio.Semaphore(max(1, self._settings.graph_extract_concurrency))

        logger.info("开始构建知识图谱：片段数=%d，并发=%d", len(texts), sem._value)
        results = await asyncio.gather(
            *(self._extract_one(llm, sem, t) for t in texts)
        )
        triples: List[Tuple[str, str, str]] = [t for sub in results for t in sub]

        graph = self._aggregate(triples)
        self._persist(graph)
        logger.info(
            "知识图谱构建完成：节点=%d，边=%d", len(graph.nodes), len(graph.edges)
        )
        return graph
