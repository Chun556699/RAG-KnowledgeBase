"""
LLM 提供商抽象层。

定义统一的消息结构与 `BaseLLMProvider` 抽象接口，所有具体提供商
（DeepSeek / 小米 MiMo，均兼容 OpenAI 协议）均实现该接口，从而实现「一次编码、
多模型可切换」。上层业务只依赖抽象，不感知底层厂商差异。
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, Dict, List, Optional


class Role(str, Enum):
    """对话消息角色。"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class Message:
    """
    统一的对话消息结构。

    Attributes:
        role: 消息角色（system/user/assistant）。
        content: 消息文本内容。
    """

    role: Role
    content: str

    def to_dict(self) -> Dict[str, str]:
        """转换为 OpenAI 风格的字典，便于直接传给各厂商 SDK。"""
        return {"role": self.role.value, "content": self.content}


@dataclass
class LLMResponse:
    """
    LLM 生成结果。

    Attributes:
        content: 生成的文本内容。
        model: 实际使用的模型名。
        provider: 提供商标识。
        prompt_tokens: 输入 token 数（若厂商返回）。
        completion_tokens: 输出 token 数（若厂商返回）。
        raw: 原始响应，便于调试。
    """

    content: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw: Optional[dict] = field(default=None, repr=False)

    @property
    def total_tokens(self) -> int:
        """总 token 消耗。"""
        return self.prompt_tokens + self.completion_tokens


@dataclass
class GenerationConfig:
    """
    生成参数配置。

    Attributes:
        temperature: 采样温度，越高越随机。
        max_tokens: 最大生成 token 数。
        top_p: 核采样阈值。
        stop: 停止词列表。
    """

    temperature: float = 0.7
    max_tokens: int = 1024
    top_p: float = 1.0
    stop: Optional[List[str]] = None


class BaseLLMProvider(abc.ABC):
    """
    LLM 提供商抽象基类。

    子类必须实现 `generate`（一次性生成）与 `stream`（流式生成）两个方法。
    """

    #: 提供商名称，子类需覆盖。
    name: str = "base"

    def __init__(self, model: str) -> None:
        """
        Args:
            model: 该提供商使用的模型名。
        """
        self.model = model

    @abc.abstractmethod
    async def generate(
        self,
        messages: List[Message],
        config: Optional[GenerationConfig] = None,
    ) -> LLMResponse:
        """
        一次性生成完整回复。

        Args:
            messages: 对话消息列表。
            config: 生成参数，为 None 时使用默认值。

        Returns:
            LLMResponse: 生成结果。

        Raises:
            ProviderError: 当底层 API 调用失败时。
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def stream(
        self,
        messages: List[Message],
        config: Optional[GenerationConfig] = None,
    ) -> AsyncIterator[str]:
        """
        流式生成回复，逐块 yield 文本增量。

        Args:
            messages: 对话消息列表。
            config: 生成参数。

        Yields:
            str: 文本增量片段。
        """
        raise NotImplementedError
        # 让类型检查器识别这是异步生成器
        yield ""  # pragma: no cover
