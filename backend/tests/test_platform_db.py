"""
平台数据库（PlatformDB）单元测试：知识库 + API 密钥生命周期。
"""

import pytest

from app.core.platform_db import KEY_PREFIX, PlatformDB


@pytest.fixture
def platform(tmp_path) -> PlatformDB:
    db = PlatformDB(str(tmp_path / "platform.db"))
    yield db
    db.close()


class TestKnowledgeBases:
    def test_default_kb_seeded(self, platform):
        kbs = platform.list_kbs()
        assert any(k.kb_id == "default" for k in kbs)

    def test_create_and_get(self, platform):
        kb = platform.create_kb("法务知识库", "合同与法规")
        assert kb.kb_id.startswith("kb_")
        got = platform.get_kb(kb.kb_id)
        assert got is not None and got.name == "法务知识库"

    def test_persistence_across_reopen(self, tmp_path):
        path = str(tmp_path / "p.db")
        db = PlatformDB(path)
        kb = db.create_kb("产品手册")
        db.close()
        db2 = PlatformDB(path)
        assert db2.get_kb(kb.kb_id) is not None
        db2.close()


class TestApiKeys:
    def test_create_key_format_and_verify(self, platform):
        record, raw = platform.create_key("web-widget", scopes=["ask"])
        assert raw.startswith(KEY_PREFIX)
        assert len(raw) == len(KEY_PREFIX) + 40
        assert record.key_prefix == raw[:14] + "…"
        info = platform.verify_key(raw)
        assert info is not None
        assert info.key_id == record.key_id
        assert info.scopes == ["ask"]

    def test_verify_rejects_wrong_and_revoked(self, platform):
        record, raw = platform.create_key("t", scopes=["ask"])
        assert platform.verify_key("ak_live_" + "0" * 40) is None
        assert platform.verify_key("") is None
        assert platform.verify_key("not-a-key") is None
        assert platform.revoke_key(record.key_id) is True
        assert platform.verify_key(raw) is None

    def test_key_bound_to_kb(self, platform):
        kb = platform.create_kb("私有库")
        record, raw = platform.create_key("bound", scopes=["ask"], kb_id=kb.kb_id)
        info = platform.verify_key(raw)
        assert info.kb_id == kb.kb_id

    def test_list_keys_masks_raw(self, platform):
        _, raw = platform.create_key("a", scopes=["ask"])
        keys = platform.list_keys()
        assert all(k.key_id for k in keys)
        # 列表中不应出现完整明文
        for k in keys:
            assert raw not in repr(k)

    def test_revoke_unknown_key(self, platform):
        assert platform.revoke_key("key_doesnotexist") is False
