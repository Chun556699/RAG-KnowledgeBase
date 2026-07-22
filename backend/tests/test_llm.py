"""
LLM 层测试。

覆盖：
- OpenAICompatibleProvider 的构造校验（缺少密钥应报错）；
- LLMFactory 的实例化、缓存、运行时切换与可用模型清单。

不发起任何真实网络请求：仅验证工厂装配与提供商构造逻辑。
"""

from __future__ import annotations

import pytest

from app.config import Settings, get_settings
from app.core.llm.factory import LLMFactory
from app.core.llm.openai_compatible import OpenAICompatibleProvider
from app.utils.exceptions import ProviderError, ValidationError


def _settings_with_keys() -> Settings:
    """构造带有测试密钥的配置（避免因缺密钥而无法实例化 provider）。"""
    return Settings(deepseek_api_key="sk-test-deepseek", mimo_api_key="sk-test-mimo")


# ---------------- OpenAICompatibleProvider ----------------
def test_provider_requires_api_key():
    """缺少 API Key 时构造应抛出 ProviderError。"""
    with pytest.raises(ProviderError):
        OpenAICompatibleProvider(
            name="deepseek", model="deepseek-chat", api_key="", base_url="https://x/v1"
        )


def test_provider_sets_name_and_model():
    """构造成功后应正确设置提供商名与模型名。"""
    provider = OpenAICompatibleProvider(
        name="mimo",
        model="mimo-7b-rl",
        api_key="sk-test",
        base_url="https://api.mimo.chat/v1",
    )
    assert provider.name == "mimo"
    assert provider.model == "mimo-7b-rl"


# ---------------- LLMFactory ----------------
def test_factory_get_deepseek_provider():
    """工厂应能创建 DeepSeek 提供商实例。"""
    factory = LLMFactory(_settings_with_keys())
    provider = factory.get_provider("deepseek")
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.name == "deepseek"


def test_factory_caches_instances():
    """相同 provider+model 应命中缓存返回同一实例。"""
    factory = LLMFactory(_settings_with_keys())
    p1 = factory.get_provider("mimo", "mimo-7b-rl")
    p2 = factory.get_provider("mimo", "mimo-7b-rl")
    assert p1 is p2


def test_factory_invalid_provider_raises():
    """不支持的 provider 应抛出 ValidationError。"""
    factory = LLMFactory(get_settings())
    with pytest.raises(ValidationError):
        factory.get_provider("not_a_provider")


def test_factory_available_models():
    """可用模型清单应仅包含 deepseek 与 mimo 两个提供商。"""
    factory = LLMFactory(get_settings())
    models = factory.available_models()
    providers = {m["provider"] for m in models}
    assert providers == {"deepseek", "mimo"}


def test_factory_available_reflects_api_key():
    """配置了密钥的提供商应标记为 available=True。"""
    factory = LLMFactory(_settings_with_keys())
    models = {m["provider"]: m for m in factory.available_models()}
    assert models["deepseek"]["available"] is True
    assert models["mimo"]["available"] is True
