"""设置 API 的原子性回归测试。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.api.settings import update_embedding_config
from app.config import Settings
from app.core.config_store import RuntimeConfigStore
from app.models.schemas import EmbeddingConfigUpdateRequest
from app.utils.exceptions import ProviderError


@pytest.mark.asyncio
async def test_failed_embedding_reload_rolls_back_persisted_override(tmp_path):
    """嵌入重建失败时不得把无效 provider 留在 runtime_config.json。"""
    config_path = tmp_path / "runtime_config.json"
    store = RuntimeConfigStore(
        Settings(embedding_provider="mock"), path=str(config_path)
    )
    container = SimpleNamespace(
        config_store=store,
        reload_embedding=Mock(side_effect=[ProviderError("invalid embedding"), None]),
    )
    req = EmbeddingConfigUpdateRequest(provider="openai")

    with pytest.raises(ProviderError):
        await update_embedding_config(req, container)

    assert store.effective_embedding()["provider"] == "mock"
    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["embedding"].get("provider") != "openai"
    assert container.reload_embedding.call_count == 2
