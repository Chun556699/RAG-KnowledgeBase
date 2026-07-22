"""
重排序（Rerank）模块。

在「向量召回」之后引入第二阶段的 Cross-Encoder 精排：向量检索（bi-encoder）
先快速召回一批候选，再由重排序模型（cross-encoder，如 BAAI/bge-reranker-v2-m3）
对 query 与每个候选逐对打分并重排，显著提升相关性排序质量。

设计与嵌入层一致：统一抽象 + 可插拔实现 + 兜底降级。
- ``NoOpReranker``：不做重排，原样截断（未配置/未启用时使用，保证零副作用）；
- ``SiliconFlowReranker``：调用 OpenAI 兼容的 ``/rerank`` 端点（硅基流动等）。

任何远端调用失败都会被捕获并降级为原始候选顺序，绝不阻断检索主流程。
"""

from __future__ import annotations

import abc
from typing import List

from app.core.rag.vectorstore import RetrievedChunk
from app.utils.logger import get_logger

logger = get_logger(__name__)


class BaseReranker(abc.ABC):
    """重排序器抽象基类。"""

    #: 是否为「有效」的重排序器（NoOp 为 False，据此决定检索是否走两阶段）。
    enabled: bool = False

    @abc.abstractmethod
    def rerank(
        self,
        query: str,
        chunks: List[RetrievedChunk],
        top_n: int,
    ) -> List[RetrievedChunk]:
        """
        对候选片段重排并返回前 top_n 条。

        Args:
            query: 查询文本。
            chunks: 向量召回的候选片段。
            top_n: 精排后保留的条数。

        Returns:
            List[RetrievedChunk]: 重排后的片段（score 更新为重排相关性分数）。
        """
        raise NotImplementedError


class NoOpReranker(BaseReranker):
    """空实现：不做任何重排，仅按原顺序截断。用于未启用/未配置密钥时的兜底。"""

    enabled = False

    def rerank(
        self,
        query: str,
        chunks: List[RetrievedChunk],
        top_n: int,
    ) -> List[RetrievedChunk]:
        """原样返回前 top_n 条。"""
        return chunks[:top_n]


class SiliconFlowReranker(BaseReranker):
    """
    OpenAI 兼容的 ``/rerank`` 重排序器。

    适用于硅基流动 SiliconFlow（BAAI/bge-reranker-v2-m3）等实现 rerank 协议的服务。
    请求体：{model, query, documents, top_n, return_documents:false}；
    响应体：{results: [{index, relevance_score}, ...]}。
    """

    enabled = True

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str,
        timeout: float = 20.0,
    ) -> None:
        """
        Args:
            model: 重排序模型名（如 BAAI/bge-reranker-v2-m3）。
            api_key: 服务 API Key。
            base_url: OpenAI 兼容端点（如 https://api.siliconflow.cn/v1）。
            timeout: 请求超时时间（秒）。
        """
        self._model = model
        self._api_key = api_key
        self._endpoint = base_url.rstrip("/") + "/rerank"
        self._timeout = timeout

    def rerank(
        self,
        query: str,
        chunks: List[RetrievedChunk],
        top_n: int,
    ) -> List[RetrievedChunk]:
        """调用远端重排序服务，失败时降级为原始候选顺序。"""
        if not chunks:
            return []
        try:
            import httpx

            resp = httpx.post(
                self._endpoint,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "query": query,
                    "documents": [c.text for c in chunks],
                    "top_n": min(top_n, len(chunks)),
                    "return_documents": False,
                },
                timeout=self._timeout,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
        except Exception as exc:  # noqa: BLE001  重排失败不阻断检索，降级返回
            logger.warning("重排序调用失败，降级为向量检索结果: %s", exc)
            return chunks[:top_n]

        reranked: List[RetrievedChunk] = []
        for item in results:
            idx = item.get("index")
            if idx is None or not (0 <= idx < len(chunks)):
                continue
            src = chunks[idx]
            reranked.append(
                RetrievedChunk(
                    chunk_id=src.chunk_id,
                    text=src.text,
                    score=round(float(item.get("relevance_score", 0.0)), 4),
                    metadata=src.metadata,
                )
            )
        # 若服务未返回有效结果，退回原始顺序，避免误伤
        return reranked[:top_n] if reranked else chunks[:top_n]


def create_reranker(config: dict) -> BaseReranker:
    """
    重排序器工厂。

    Args:
        config: 重排序有效配置，含 enabled / api_key / base_url / model / timeout。

    Returns:
        BaseReranker: 启用且配置了密钥时返回 SiliconFlowReranker，否则返回 NoOpReranker。
    """
    if config.get("enabled") and config.get("api_key"):
        logger.info("重排序已启用：model=%s", config.get("model"))
        return SiliconFlowReranker(
            model=str(config.get("model") or ""),
            api_key=str(config.get("api_key") or ""),
            base_url=str(config.get("base_url") or ""),
            timeout=float(config.get("timeout") or 20.0),
        )
    return NoOpReranker()
