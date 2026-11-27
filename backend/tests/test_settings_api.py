"""设置 API 的配置验证回归测试。"""

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
async def test_invalid_embedding_config_is_rejected_before_persist(tmp_path, monkeypatch):
    """无效嵌入配置必须先验证失败，不得写入 runtime_config.json。"""
    config_path = tmp_path / "runtime_config.json"
    store = RuntimeConfigStore(
        Settings(embedding_provider="mock"), path=str(config_path)
    )
    reload_embedding = Mock()
    container = SimpleNamespace(config_store=store, reload_embedding=reload_embedding)
    monkeypatch.setattr(
        "app.api.settings.create_embedder",
        Mock(side_effect=ProviderError("invalid embedding")),
    )
    req = EmbeddingConfigUpdateRequest(provider="openai")

    with pytest.raises(ProviderError):
        await update_embedding_config(req, container)

    assert store.effective_embedding()["provider"] == "mock"
    assert not config_path.exists() or json.loads(config_path.read_text(encoding="utf-8"))[
        "embedding"
    ].get("provider") != "openai"
    reload_embedding.assert_not_called()
