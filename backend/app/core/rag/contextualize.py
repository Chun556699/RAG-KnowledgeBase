"""
Contextual Retrieval（上下文增强检索）—— Anthropic 提出的索引期增强技术。

思路：嵌入前，为每个片段生成一句「该片段在原文中的语境说明」前缀
（如「本文是公司 2024 年 Q3 财报；本段讨论营收构成」），
使片段嵌入携带全局上下文，显著降低指代缺失导致的检索失败。

代价：摄取时每个片段一次 LLM 调用（受并发信号量限流）。
仅在配置开启且 LLM 可用时启用；任何失败降级为空前缀，不阻断索引。
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

from app.core.llm.base import GenerationConfig, Message, Role
from app.core.llm.prompt import get_template
from app.utils.logger import get_logger

logger = get_logger(__name__)


class Contextualizer:
    """为片段批量生成上下文前缀（并发限流 + 失败降级）。"""

    def __init__(self, llm_factory, concurrency: int = 4) -> None:
        """
        Args:
            llm_factory: LLM 工厂（取默认提供商）。
            concurrency: 并发度上限（asyncio 信号量）。
        """
        self._llm_factory = llm_factory
        self._sem = asyncio.Semaphore(concurrency)

    async def build_contexts(
        self, doc_excerpt: str, chunks: List[str]
    ) -> List[Optional[str]]:
        """
        为每个片段生成上下文前缀。

        Args:
            doc_excerpt: 文档开头摘录（给 LLM 的全局背景，建议前 1~2 千字）。
            chunks: 片段文本列表。

        Returns:
            List[Optional[str]]: 与 chunks 对齐的前缀列表；失败项为 None。
        """
        try:
            llm = self._llm_factory.get_provider()
        except Exception as exc:  # noqa: BLE001 无可用 LLM 则整体跳过
            logger.warning("Contextual Retrieval 需要 LLM，当前不可用，跳过: %s", exc)
            return [None] * len(chunks)

        async def _one(chunk: str) -> Optional[str]:
            async with self._sem:
                try:
                    prompt = get_template("context_prefix").render(
                        document=doc_excerpt, chunk=chunk
                    )
                    resp = await llm.generate(
                        [Message(Role.USER, prompt)],
                        GenerationConfig(temperature=0.0, max_tokens=80),
                    )
                    ctx = (resp.content or "").strip().strip('"').strip()
                    # 只保留一句话内、非空的前缀
                    if ctx and len(ctx) <= 200:
                        return ctx
                    return None
                except Exception as exc:  # noqa: BLE001 单块失败不阻断批量
                    logger.warning("上下文前缀生成失败，跳过该块: %s", exc)
                    return None

        results = await asyncio.gather(*(_one(c) for c in chunks))
        ok = sum(1 for r in results if r)
        logger.info("Contextual Retrieval：%d/%d 块生成上下文前缀", ok, len(chunks))
        return list(results)
