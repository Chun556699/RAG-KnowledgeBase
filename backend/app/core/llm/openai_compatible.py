"""
OpenAI 兼容 LLM 提供商。

DeepSeek 与小米 MiMo 均实现 OpenAI Chat Completions 协议，故统一由本类封装：
只需传入不同的 `name` / `model` / `api_key` / `base_url` 即可复用同一套逻辑，
支持一次性与流式生成。
"""

from __future__ import annotations

from typing import AsyncIterator, List, Optional

from app.core.llm.base import (
    BaseLLMProvider,
    GenerationConfig,
    LLMResponse,
    Message,
)
from app.utils.exceptions import ProviderError
from app.utils.logger import get_logger

logger = get_logger(__name__)


class OpenAICompatibleProvider(BaseLLMProvider):
    """封装任意 OpenAI 协议兼容服务（DeepSeek / MiMo）。"""

    def __init__(
        self,
        name: str,
        model: str,
        api_key: str,
        base_url: str,
    ) -> None:
        """
        Args:
            name: 提供商标识（deepseek / mimo）。
            model: 模型名，如 deepseek-chat。
            api_key: 该服务的 API Key。
            base_url: OpenAI 兼容端点地址。

        Raises:
            ProviderError: 缺少 API Key 或 SDK 未安装时。
        """
        super().__init__(model)
        self.name = name
        if not api_key:
            raise ProviderError(
                f"使用 {name} provider 需配置 {name.upper()}_API_KEY"
            )
        try:
            # 延迟导入，避免未安装 SDK 时影响其他逻辑
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover
            raise ProviderError("未安装 openai SDK，请执行 pip install openai") from exc

        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def generate(
        self,
        messages: List[Message],
        config: Optional[GenerationConfig] = None,
    ) -> LLMResponse:
        """调用 Chat Completions 一次性生成。"""
        cfg = config or GenerationConfig()
        try:
            resp = await self._client.chat.completions.create(
                model=self.model,
                messages=[m.to_dict() for m in messages],
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
                top_p=cfg.top_p,
                stop=cfg.stop,
            )
        except Exception as exc:  # noqa: BLE001  统一转换为业务异常
            logger.error("%s 生成失败: %s", self.name, exc)
            raise ProviderError(f"{self.name} 调用失败: {exc}") from exc

        choice = resp.choices[0]
        usage = resp.usage
        return LLMResponse(
            content=choice.message.content or "",
            model=resp.model,
            provider=self.name,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            raw=resp.model_dump(),
        )

    async def stream(
        self,
        messages: List[Message],
        config: Optional[GenerationConfig] = None,
    ) -> AsyncIterator[str]:
        """流式生成，逐块返回增量文本。"""
        cfg = config or GenerationConfig()
        try:
            stream = await self._client.chat.completions.create(
                model=self.model,
                messages=[m.to_dict() for m in messages],
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
                top_p=cfg.top_p,
                stop=cfg.stop,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as exc:  # noqa: BLE001
            logger.error("%s 流式生成失败: %s", self.name, exc)
            raise ProviderError(f"{self.name} 流式调用失败: {exc}") from exc
