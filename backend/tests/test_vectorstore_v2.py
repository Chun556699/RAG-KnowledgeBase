"""
向量库 v2（二进制向量 + SQLite 元数据）专项测试。

覆盖：持久化格式、跨重启加载、kb_id 租户过滤、embed_texts 双通道嵌入、
软删除与压缩、旧版 JSON 自动迁移、版本号。
"""

from __future__ import annotations

import json
import os

from app.core.rag.embeddings import MockEmbedder
from app.core.rag.vectorstore import VectorStore


def _make_store(tmp_path) -> VectorStore:
    return VectorStore(
        persist_path=str(tmp_path / "vectorstore.json"),
        embedder=MockEmbedder(dimension=128),
    )


class TestPersistenceFormat:
    def test_writes_bin_and_meta_db(self, tmp_path):
        """v2 应写 .bin（向量）与 .meta.db（元数据），不再写 JSON 主文件。"""
        store = _make_store(tmp_path)
        store.add_chunks(["c1"], ["测试文本"], [{"document_id": "d1"}])
        store.close()
        assert os.path.exists(tmp_path / "vectorstore.bin")
        assert os.path.exists(tmp_path / "vectorstore.meta.db")

    def test_reload_after_close(self, tmp_path):
        """重启（重建实例）后数据仍在且可检索。"""
        store = _make_store(tmp_path)
        store.add_chunks(
            ["c1", "c2"],
            ["机器学习入门", "烹饪技巧大全"],
            [{"document_id": "d1"}, {"document_id": "d2"}],
        )
        store.close()

        store2 = _make_store(tmp_path)
        assert store2.count() == 2
        results = store2.query("机器学习", top_k=1)
        assert results and results[0].text == "机器学习入门"
        store2.close()


class TestKbIsolation:
    def test_count_and_filter_by_kb(self, tmp_path):
        store = _make_store(tmp_path)
        store.add_chunks(
            ["a1", "b1"],
            ["相同的文本", "相同的文本"],
            [{"document_id": "d1", "kb_id": "kb_a"}, {"document_id": "d2", "kb_id": "kb_b"}],
        )
        assert store.count() == 2
        assert store.count({"kb_id": "kb_a"}) == 1
        results = store.query("文本", where={"kb_id": "kb_b"})
        assert len(results) == 1
        assert results[0].metadata["kb_id"] == "kb_b"

    def test_all_chunks_filter(self, tmp_path):
        store = _make_store(tmp_path)
        store.add_chunks(
            ["a1", "b1"],
            ["文本A", "文本B"],
            [{"document_id": "d1", "kb_id": "kb_a"}, {"document_id": "d2", "kb_id": "kb_b"}],
        )
        assert len(store.all_chunks({"kb_id": "kb_a"})) == 1
        assert len(store.all_chunks()) == 2


class TestEmbedTexts:
    def test_embed_texts_separate_from_display(self, tmp_path):
        """embed_texts 用于嵌入（Contextual Retrieval），texts 用于展示。"""
        store = _make_store(tmp_path)
        store.add_chunks(
            ["c1"],
            ["收益增长 20%"],
            [{"document_id": "d1"}],
            embed_texts=["本段摘自年度财报：收益增长 20%"],
        )
        # 显示文本是原文
        assert store.all_chunks()[0].text == "收益增长 20%"
        # 用前缀内容应也能命中（向量来自 embed_texts）
        results = store.query("年度财报", top_k=1)
        assert results and results[0].chunk_id == "c1"


class TestDeletionAndVersion:
    def test_soft_delete_and_version_bump(self, tmp_path):
        store = _make_store(tmp_path)
        v0 = store.version
        store.add_chunks(
            ["c1", "c2"], ["文本1", "文本2"], [{"document_id": "d1"}, {"document_id": "d2"}]
        )
        assert store.version > v0
        store.delete_by_document("d1")
        assert store.count() == 1
        results = store.query("文本", top_k=5)
        assert all(r.text != "文本1" for r in results)

    def test_delete_persists_across_reload(self, tmp_path):
        store = _make_store(tmp_path)
        store.add_chunks(
            ["c1"], ["要删除的文本"], [{"document_id": "d1"}]
        )
        store.delete_by_document("d1")
        store.close()
        store2 = _make_store(tmp_path)
        assert store2.count() == 0
        store2.close()


class TestLegacyMigration:
    def test_migrates_legacy_json(self, tmp_path):
        """启动时若发现旧版 vectorstore.json，自动迁移到 v2 并重命名旧文件。"""
        legacy = tmp_path / "vectorstore.json"
        emb = MockEmbedder(dimension=128)
        vecs = emb.embed_documents(["迁移的文本"])
        legacy.write_text(
            json.dumps(
                {
                    "ids": ["c1"],
                    "texts": ["迁移的文本"],
                    "metadatas": [{"document_id": "d1"}],
                    "vectors": [vecs[0]],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        store = _make_store(tmp_path)
        assert store.count() == 1
        assert store.all_chunks()[0].text == "迁移的文本"
        # 旧文件被改名存档
        assert not legacy.exists()
        assert (tmp_path / "vectorstore.json.bak").exists()
        store.close()
