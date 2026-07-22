"""
文本嵌入（Embedding）模块。

提供统一的嵌入抽象，采用 **离线确定性 Mock 嵌入**：
基于「哈希词袋 + L2 归一化」，无需下载模型或联网即可产生可用于语义检索的
稠密向量，保证项目开箱即用。（DeepSeek / MiMo 不提供嵌入接口，故嵌入层独立于 LLM 提供商）
"""

from __future__ import annotations

import abc
import hashlib
import math
import re
from typing import List

from app.utils.exceptions import ProviderError
from app.utils.logger import get_logger

logger = get_logger(__name__)


class BaseEmbedder(abc.ABC):
    """嵌入器抽象基类。"""

    #: 向量维度，子类需设置。
    dimension: int

    @abc.abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量嵌入文档文本。"""
        raise NotImplementedError

    def embed_query(self, text: str) -> List[float]:
        """
        嵌入单条查询文本。默认复用 embed_documents。

        Args:
            text: 查询文本。

        Returns:
            List[float]: 查询向量。
        """
        return self.embed_documents([text])[0]


class MockEmbedder(BaseEmbedder):
    """
    离线确定性嵌入器。

    原理：对文本做分词（中英文），将每个 token 通过哈希映射到固定维度的桶中
    累加词频，再做 L2 归一化。相同文本恒得相同向量，语义相近（共享词汇多）的
    文本余弦相似度更高，足以支撑演示级语义检索，且完全离线、零依赖模型。
    """

    def __init__(self, dimension: int = 384) -> None:
        """
        Args:
            dimension: 输出向量维度。
        """
        self.dimension = dimension

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """简易分词：提取英文单词，并将中文按单字切分。"""
        text = text.lower()
        # 英文/数字连续串
        tokens = re.findall(r"[a-z0-9]+", text)
        # 中文单字
        tokens += re.findall(r"[\u4e00-\u9fff]", text)
        return tokens

    def _hash_bucket(self, token: str) -> int:
        """将 token 稳定映射到 [0, dimension) 的桶索引。"""
        digest = hashlib.md5(token.encode("utf-8")).hexdigest()
        return int(digest, 16) % self.dimension

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量嵌入（见基类文档）。"""
        vectors: List[List[float]] = []
        for text in texts:
            vec = [0.0] * self.dimension
            for token in self._tokenize(text):
                vec[self._hash_bucket(token)] += 1.0
            # L2 归一化，使余弦相似度只与方向有关
            norm = math.sqrt(sum(v * v for v in vec))
            if norm > 0:
                vec = [v / norm for v in vec]
            vectors.append(vec)
        return vectors


class OpenAIEmbedder(BaseEmbedder):
    """已移除：请改用 OpenAICompatibleEmbedder。保留类名仅为向后兼容提示。"""

    def __init__(self, *args, **kwargs) -> None:  # noqa: D401
        raise ProviderError(
            "OpenAIEmbedder 已废弃，请使用 embedding_provider=openai（OpenAICompatibleEmbedder）"
        )


class OpenAICompatibleEmbedder(BaseEmbedder):
    """
    OpenAI 兼容的真实语义嵌入器。

    适用于任何实现 OpenAI Embeddings 协议的服务（如硅基流动 SiliconFlow 的 BAAI/bge-m3、
    OpenAI 的 text-embedding-3-small 等）。与 Mock 不同，它产生真正的语义向量：
    同义改写、跨语言查询也能命中，显著提升检索准确性。

    向量维度由服务端决定，首次调用后回写 dimension。
    """

    def __init__(self, model: str, api_key: str, base_url: str, batch_size: int = 32) -> None:
        """
        Args:
            model: 嵌入模型名（如 BAAI/bge-m3、text-embedding-3-small）。
            api_key: 嵌入服务的 API Key。
            base_url: OpenAI 兼容的嵌入端点地址。
            batch_size: 每次请求的最大文本条数（避免超过服务端批量上限）。

        Raises:
            ProviderError: 缺少 API Key 或 SDK 未安装时。
        """
        if not api_key:
            raise ProviderError(
                "使用 openai 嵌入需配置 EMBEDDING_API_KEY"
            )
        try:
            # 延迟导入，避免未安装 SDK 时影响其他逻辑
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise ProviderError("未安装 openai SDK，请执行 pip install openai") from exc

        self._model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._batch_size = max(1, batch_size)
        # 维度待首次调用后确定（不同模型维度不同）
        self.dimension = 0

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量调用嵌入 API（按 batch_size 分批，避免超服务端上限）。"""
        if not texts:
            return []
        vectors: List[List[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            try:
                resp = self._client.embeddings.create(model=self._model, input=batch)
            except Exception as exc:  # noqa: BLE001  统一转为业务异常
                logger.error("嵌入 API 调用失败: %s", exc)
                raise ProviderError(f"嵌入服务调用失败: {exc}") from exc
            vectors.extend(item.embedding for item in resp.data)
        if vectors and not self.dimension:
            self.dimension = len(vectors[0])
        return vectors


def create_embedder(
    provider: str,
    *,
    dimension: int = 384,
    api_key: str = "",
    base_url: str = "",
    model: str = "",
    **_ignored,
) -> BaseEmbedder:
    """
    嵌入器工厂。

    - "mock"：离线确定性词袋嵌入，无需密钥，开箱即用（默认）；
    - "openai"：OpenAI 兼容的真实语义嵌入，需配置 api_key/base_url/model。

    Args:
        provider: 嵌入提供商（mock / openai）。
        dimension: Mock 嵌入的向量维度（仅 mock 生效）。
        api_key: openai 嵌入的密钥。
        base_url: openai 兼容嵌入端点。
        model: openai 嵌入模型名。

    Returns:
        BaseEmbedder: 嵌入器实例。

    Raises:
        ProviderError: provider 不受支持时。
    """
    provider = provider.lower().strip()
    if provider == "mock":
        return MockEmbedder(dimension)
    if provider == "openai":
        return OpenAICompatibleEmbedder(model=model, api_key=api_key, base_url=base_url)
    raise ProviderError(f"不支持的嵌入提供商: {provider}（可选: mock / openai）")
