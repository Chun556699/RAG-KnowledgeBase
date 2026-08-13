"""
LLM 工厂与注册中心。

职责：
1. 根据 provider 名称构造对应的 LLM 实例（支持运行时切换）；
2. 缓存已创建的实例，避免重复初始化客户端；
3. 暴露「可用模型清单」供前端下拉选择。

本项目仅保留 **DeepSeek** 与 **小米 MiMo** 两个提供商，二者均兼容 OpenAI
Chat Completions 协议，统一由 `OpenAICompatibleProvider` 封装。业务层只需调用
`get_provider(name)` 即可在二者间无缝切换。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from app.config import Settings, get_settings
from app.core.llm.base import BaseLLMProvider
from app.core.llm.openai_compatible import OpenAICompatibleProvider
from app.utils.exceptions import ValidationError
from app.utils.logger import get_logger

logger = get_logger(__name__)


class LLMFactory:
    """LLM 提供商工厂，负责实例化与缓存。"""

    def __init__(self, settings: Settings, config_store: Optional[object] = None) -> None:
        """
        Args:
            settings: 全局只读配置（作为凭据默认值）。
            config_store: 运行时配置存储（RuntimeConfigStore）。提供时优先从其
                读取有效凭据，以支持网页端运行时修改密钥/端点。
        """
        self._settings = settings
        self._store = config_store
        # 缓存已构造的实例：key 为 "provider:model"
        self._cache: Dict[str, BaseLLMProvider] = {}

    def _provider_configs(self) -> Dict[str, dict]:
        """各提供商的连接配置（默认模型 / 端点 / 密钥）。

        提供了运行时配置存储时从其读取（支持网页端接入与切换），
        否则回落到 .env 基线。
        """
        if self._store is not None:
            return self._store.llm_configs()
        s = self._settings
        return {
            "deepseek": {
                "model": s.deepseek_model,
                "api_key": s.deepseek_api_key,
                "base_url": s.deepseek_base_url,
                "description": "DeepSeek 深度求索（OpenAI 兼容）",
            },
            "mimo": {
                "model": s.mimo_model,
                "api_key": s.mimo_api_key,
                "base_url": s.mimo_base_url,
                "description": "小米 MiMo（OpenAI 兼容）",
            },
        }

    def invalidate(self) -> None:
        """清空实例缓存（凭据变更后调用，使新密钥/端点/模型下次生效）。"""
        self._cache.clear()
        logger.info("LLM 工厂实例缓存已清空（凭据变更）")

    def get_provider(self, provider: str, model: str | None = None) -> BaseLLMProvider:
        """
        获取指定提供商实例。

        Args:
            provider: 提供商名（deepseek / mimo）。
            model: 模型名，为 None 时使用该提供商的默认模型。

        Returns:
            BaseLLMProvider: 提供商实例。

        Raises:
            ValidationError: 当 provider 不受支持时。
        """
        provider = provider.lower().strip()
        configs = self._provider_configs()
        if provider not in configs:
            raise ValidationError(
                f"不支持的 LLM 提供商: {provider}，可选: {list(configs)}"
            )

        cfg = configs[provider]
        resolved_model = model or cfg["model"]
        cache_key = f"{provider}:{resolved_model}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        logger.info("初始化 LLM 提供商: %s (model=%s)", provider, resolved_model)
        instance = OpenAICompatibleProvider(
            name=provider,
            model=resolved_model,
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
        )
        self._cache[cache_key] = instance
        return instance

    def default_provider_name(self) -> str:
        """获取默认提供商名称（运行时配置优先，回落到 .env）。"""
        if self._store is not None:
            return self._store.default_provider()
        return self._settings.default_llm_provider

    def get_default(self) -> BaseLLMProvider:
        """获取默认提供商实例（运行时配置优先，回落到 .env）。"""
        return self.get_provider(self.default_provider_name())

    def available_models(self) -> List[dict]:
        """
        列出可用模型清单，供前端展示与切换。

        仅当对应 API Key 已配置时，才将提供商标记为 available=True。

        Returns:
            List[dict]: 每项含 provider/model/available/description。
        """
        configs = self._provider_configs()
        return [
            {
                "provider": name,
                "model": cfg["model"],
                "available": bool(cfg["api_key"]),
                "description": cfg["description"],
            }
            for name, cfg in configs.items()
        ]


# 全局工厂单例
_factory: LLMFactory | None = None


def get_llm_factory() -> LLMFactory:
    """获取全局 LLM 工厂单例（与运行时配置存储装配）。"""
    global _factory
    if _factory is None:
        # 延迟导入避免循环依赖（config_store 依赖 config）
        from app.core.config_store import get_config_store

        _factory = LLMFactory(get_settings(), config_store=get_config_store())
    return _factory


def reset_llm_factory() -> None:
    """重置全局工厂单例（主要用于测试隔离）。"""
    global _factory
    _factory = None
