"""
向量存储模块（本地高性能向量库 v2）。

架构（相对旧版 numpy+JSON 的升级）：
- 向量以 **float32 二进制文件追加写**（`*.bin`），写入 O(1)，不再整库 JSON 重写；
- 文本/元数据存 **SQLite**（`*.meta.db`），支持按 document_id / kb_id 索引过滤；
- 内存中维护 **入库即 L2 归一化** 的向量矩阵，检索时一次 BLAS 点积即得余弦相似度；
- 删除采用「标记删除 + 惰性掩码」，启动时若删除占比过高自动压缩重建；
- 启动时自动从旧版 `vectorstore.json` 一次性迁移，老数据不丢失。

关键设计保持与旧版一致：**嵌入计算由外部 Embedder 完成**，本库仅负责向量索引、
持久化与相似度检索，从而与嵌入提供商解耦。
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from app.core.rag.embeddings import BaseEmbedder
from app.utils.logger import get_logger

logger = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    row         INTEGER PRIMARY KEY,
    chunk_id    TEXT NOT NULL UNIQUE,
    document_id TEXT NOT NULL DEFAULT '',
    kb_id       TEXT NOT NULL DEFAULT 'default',
    text        TEXT NOT NULL,
    metadata    TEXT NOT NULL DEFAULT '{}',
    deleted     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_kb  ON chunks(kb_id);
"""


@dataclass
class RetrievedChunk:
    """
    检索命中的文档片段。

    Attributes:
        chunk_id: 片段唯一 ID。
        text: 片段文本。
        score: 相似度分数（0~1，越大越相关）。
        metadata: 附加元数据（文档 ID、文件名、块序号、知识库 ID 等）。
    """

    chunk_id: str
    text: str
    score: float
    metadata: Dict[str, str]


class VectorStore:
    """
    本地持久化向量存储：float32 二进制向量文件 + SQLite 元数据 + 归一化内存矩阵。

    Args:
        persist_path: 持久化主路径。约定使用 ``<path 去掉 .json 后缀>.bin`` 存向量、
            ``... .meta.db`` 存元数据；若同名 ``.json`` 旧版数据存在则自动迁移。
        embedder: 嵌入器实例（负责计算向量）。
    """

    def __init__(self, persist_path: str, embedder: BaseEmbedder) -> None:
        self._embedder = embedder
        base = Path(persist_path)
        stem = base.with_suffix("") if base.suffix else base
        self._bin_path = stem.with_suffix(".bin")
        self._db_path = stem.with_suffix(".meta.db")
        self._legacy_json = base if base.suffix == ".json" else base.with_suffix(".json")
        self._lock = threading.RLock()

        # 平行结构：_ids[i] / _texts[i] / _metadatas[i] / _rows[i] / _vectors[i]
        self._ids: List[str] = []
        self._texts: List[str] = []
        self._metadatas: List[Dict[str, str]] = []
        self._rows: List[int] = []           # 每条记录在 .bin 文件中的行号
        self._dim: int = 0
        self._vectors: np.ndarray = np.empty((0, 0), dtype=np.float32)
        # 写路径递增的版本号：供检索缓存做失效判定（版本变则缓存作废）
        self._version: int = 0

        self._init_db()
        self._load()

    # ------------------------------------------------------------------
    # 初始化 / 加载 / 持久化
    # ------------------------------------------------------------------
    def _init_db(self) -> None:
        """打开（或创建）元数据 SQLite 库并建表。"""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def _load(self) -> None:
        """
        加载元数据 + 向量到内存。

        顺序：必要时先从旧版 JSON 迁移 → 读取未删除记录 → 按行号从 .bin
        拼装内存矩阵 → 若删除占比过高则压缩重建。
        """
        with self._lock:
            self._maybe_migrate_legacy()

            rows = self._db.execute(
                "SELECT row, chunk_id, text, metadata FROM chunks "
                "WHERE deleted = 0 ORDER BY row"
            ).fetchall()

            self._rows = [r[0] for r in rows]
            self._ids = [r[1] for r in rows]
            self._texts = [r[2] for r in rows]
            self._metadatas = [json.loads(r[3] or "{}") for r in rows]

            self._vectors = self._read_vectors()

            deleted_ratio = self._deleted_ratio()
            if deleted_ratio > 0.3:
                logger.info("向量库删除占比 %.0f%%，启动时压缩重建", deleted_ratio * 100)
                self._compact_locked()

            logger.info(
                "向量库就绪：bin=%s db=%s，现有条目=%d",
                self._bin_path,
                self._db_path,
                len(self._ids),
            )

    def _read_vectors(self) -> np.ndarray:
        """按存活行号从 .bin 读取并堆叠为内存矩阵（文件内已是归一化向量）。"""
        if not self._rows or not self._bin_path.exists():
            return np.empty((0, 0), dtype=np.float32)
        data = np.fromfile(str(self._bin_path), dtype=np.float32)
        dim = data.size // self._max_row_plus_one() if self._max_row_plus_one() else 0
        if dim <= 0:
            return np.empty((0, 0), dtype=np.float32)
        full = data.reshape(-1, dim)
        self._dim = dim
        return full[np.asarray(self._rows, dtype=np.int64)]

    def _max_row_plus_one(self) -> int:
        """当前已分配的最大行号 + 1（即 .bin 文件应有的行数）。"""
        row = self._db.execute("SELECT MAX(row) FROM chunks").fetchone()[0]
        return int(row) + 1 if row is not None else 0

    def _deleted_ratio(self) -> float:
        """已删除记录占总记录的比例（0~1）。"""
        total = self._db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        if not total:
            return 0.0
        deleted = self._db.execute(
            "SELECT COUNT(*) FROM chunks WHERE deleted = 1"
        ).fetchone()[0]
        return deleted / total

    def _maybe_migrate_legacy(self) -> None:
        """旧版 vectorstore.json 存在且新库为空时执行一次性迁移。"""
        if not self._legacy_json.exists():
            return
        existing = self._db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        if existing:
            return
        try:
            data = json.loads(self._legacy_json.read_text(encoding="utf-8"))
            ids: List[str] = data.get("ids", [])
            texts: List[str] = data.get("texts", [])
            metas: List[Dict[str, str]] = data.get("metadatas", [])
            vectors = np.asarray(data.get("vectors") or [], dtype=np.float32)
            if not ids or vectors.size == 0:
                return
            # 旧数据向量未归一化，入库前归一化
            vectors = self._normalize(vectors)
            self._dim = int(vectors.shape[1])
            self._append_vectors(vectors)
            with self._db:
                for row, (cid, text, meta) in enumerate(zip(ids, texts, metas)):
                    meta = meta or {}
                    self._db.execute(
                        "INSERT INTO chunks(row, chunk_id, document_id, kb_id, text, metadata)"
                        " VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            row,
                            cid,
                            meta.get("document_id", ""),
                            meta.get("kb_id", "default"),
                            text,
                            json.dumps(meta, ensure_ascii=False),
                        ),
                    )
            logger.info("已从旧版 JSON 迁移 %d 条向量到高性能存储", len(ids))
            # 迁移成功后将旧文件改名存档，避免下次启动重复迁移
            self._legacy_json.rename(self._legacy_json.with_suffix(".json.bak"))
        except Exception as exc:  # noqa: BLE001 迁移失败不阻塞启动
            logger.error("旧版向量库迁移失败，按空库启动: %s", exc)

    def _append_vectors(self, matrix: np.ndarray) -> None:
        """把归一化矩阵按行追加到 .bin 文件末尾。"""
        with self._bin_path.open("ab") as f:
            np.asarray(matrix, dtype=np.float32).tofile(f)

    def _compact_locked(self) -> None:
        """压缩重建：仅保留存活行，重写 .bin 并重排行号（调用方须持锁）。"""
        if not self._ids:
            # 全空：直接清库清文件
            self._db.execute("DELETE FROM chunks")
            self._db.commit()
            if self._bin_path.exists():
                self._bin_path.unlink()
            return
        matrix = self._vectors
        tmp = self._bin_path.with_suffix(".bin.tmp")
        with tmp.open("wb") as f:
            matrix.tofile(f)
        tmp.replace(self._bin_path)
        with self._db:
            self._db.execute("DELETE FROM chunks WHERE deleted = 1")
            for new_row, (cid, text, meta) in enumerate(
                zip(self._ids, self._texts, self._metadatas)
            ):
                self._db.execute(
                    "UPDATE chunks SET row = ? WHERE chunk_id = ?", (new_row, cid)
                )
        self._rows = list(range(len(self._ids)))

    @staticmethod
    def _normalize(matrix: np.ndarray) -> np.ndarray:
        """对每行做 L2 归一化，使点积等价于余弦相似度。"""
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return matrix / norms

    # ------------------------------------------------------------------
    # 版本号（供检索缓存失效判定）
    # ------------------------------------------------------------------
    @property
    def version(self) -> int:
        """每次写入/删除自增的版本号。"""
        return self._version

    # ------------------------------------------------------------------
    # 写入 / 删除
    # ------------------------------------------------------------------
    def add_chunks(
        self,
        chunk_ids: List[str],
        texts: List[str],
        metadatas: List[Dict[str, str]],
        embed_texts: Optional[Sequence[str]] = None,
    ) -> None:
        """
        写入文档片段（含向量）。

        Args:
            chunk_ids: 片段 ID 列表。
            texts: 片段文本列表（用于展示/拼接上下文）。
            metadatas: 片段元数据列表；``document_id`` / ``kb_id`` 会被提升为索引列。
            embed_texts: 可选。用于计算嵌入的文本（如带上下文前缀），
                缺省用 texts。实现 Contextual Retrieval 时两者不同。
        """
        if not texts:
            return
        embed_input = list(embed_texts) if embed_texts else list(texts)
        embeddings = self._embedder.embed_documents(embed_input)
        new_vectors = self._normalize(np.asarray(embeddings, dtype=np.float32))

        with self._lock:
            start_row = self._max_row_plus_one()
            self._append_vectors(new_vectors)
            with self._db:
                for i, (cid, text, meta) in enumerate(zip(chunk_ids, texts, metadatas)):
                    meta = meta or {}
                    self._db.execute(
                        "INSERT INTO chunks(row, chunk_id, document_id, kb_id, text, metadata)"
                        " VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            start_row + i,
                            cid,
                            meta.get("document_id", ""),
                            meta.get("kb_id", "default"),
                            text,
                            json.dumps(meta, ensure_ascii=False),
                        ),
                    )
            self._rows.extend(range(start_row, start_row + len(chunk_ids)))
            self._ids.extend(chunk_ids)
            self._texts.extend(texts)
            self._metadatas.extend(metadatas)
            if self._dim == 0:
                self._dim = int(new_vectors.shape[1])
            self._vectors = (
                new_vectors
                if self._vectors.size == 0
                else np.vstack([self._vectors, new_vectors])
            )
            self._version += 1
        logger.info("写入 %d 个片段到向量库", len(texts))

    def query(
        self,
        query_text: str,
        top_k: int = 4,
        where: Optional[Dict[str, str]] = None,
        min_score: float = 0.0,
    ) -> List[RetrievedChunk]:
        """
        语义检索最相关的片段（BLAS 点积 + argpartition 取 top-k）。

        Args:
            query_text: 查询文本。
            top_k: 返回条数。
            where: 元数据过滤条件（如按 document_id / kb_id 过滤）。
            min_score: 相关性阈值，低于该余弦相似度的片段被丢弃。

        Returns:
            List[RetrievedChunk]: 按相关度降序排列、且不低于阈值的片段列表。
        """
        with self._lock:
            if not self._ids:
                return []

            query_vec = np.asarray(self._embedder.embed_query(query_text), dtype=np.float32)
            # 维度守卫：切换嵌入器后若未重建索引，维度不一致时返回空并告警
            if query_vec.shape[0] != self._dim:
                logger.warning(
                    "查询向量维度(%d)与库内维度(%d)不一致，请切换嵌入后重建索引",
                    query_vec.shape[0],
                    self._dim,
                )
                return []
            norm = np.linalg.norm(query_vec)
            if norm > 0:
                query_vec = query_vec / norm
            scores = self._vectors @ query_vec  # 内存矩阵已归一化，点积即余弦

            # 元数据过滤（document_id / kb_id 走索引列，其余按 JSON 元数据匹配）
            candidate_idx = [
                i
                for i in range(len(self._ids))
                if not where
                or all(self._metadatas[i].get(k) == v for k, v in where.items())
            ]
            if not candidate_idx:
                return []

            # argpartition 取 top_k，避免对整个 N 维分数数组全排序
            cand = np.asarray(candidate_idx, dtype=np.int64)
            cand_scores = scores[cand]
            k = min(top_k, len(cand))
            part = np.argpartition(-cand_scores, k - 1)[:k]
            order = part[np.argsort(-cand_scores[part])]
            selected = cand[order]

            return [
                RetrievedChunk(
                    chunk_id=self._ids[i],
                    text=self._texts[i],
                    score=round(float(scores[i]), 4),
                    metadata=self._metadatas[i] or {},
                )
                for i in selected
                if float(scores[i]) >= min_score
            ]

    def delete_by_document(self, document_id: str) -> None:
        """删除某文档的所有片段（标记删除，下一次启动/压缩时物理回收）。"""
        with self._lock:
            rows = self._db.execute(
                "SELECT row FROM chunks WHERE document_id = ? AND deleted = 0",
                (document_id,),
            ).fetchall()
            if not rows:
                return
            row_set = {r[0] for r in rows}
            with self._db:
                self._db.execute(
                    "UPDATE chunks SET deleted = 1 WHERE document_id = ?", (document_id,)
                )
            keep = [i for i, r in enumerate(self._rows) if r not in row_set]
            self._ids = [self._ids[i] for i in keep]
            self._texts = [self._texts[i] for i in keep]
            self._metadatas = [self._metadatas[i] for i in keep]
            self._rows = [self._rows[i] for i in keep]
            self._vectors = (
                self._vectors[keep] if keep else np.empty((0, self._dim), dtype=np.float32)
            )
            self._version += 1
        logger.info("已标记删除文档 %s 的全部片段（%d 条）", document_id, len(rows))

    def count(self, where: Optional[Dict[str, str]] = None) -> int:
        """返回存活片段总数；可选按 document_id / kb_id 等元数据过滤。"""
        if not where:
            return len(self._ids)
        return sum(
            1
            for m in self._metadatas
            if all(m.get(k) == v for k, v in where.items())
        )

    def all_chunks(self, where: Optional[Dict[str, str]] = None) -> List[RetrievedChunk]:
        """
        返回库内片段（不含相似度计算，score 恒为 0）。

        Args:
            where: 可选元数据过滤（如按 kb_id 限定知识库范围）。
        """
        with self._lock:
            return [
                RetrievedChunk(
                    chunk_id=self._ids[i],
                    text=self._texts[i],
                    score=0.0,
                    metadata=self._metadatas[i] or {},
                )
                for i in range(len(self._ids))
                if not where
                or all(self._metadatas[i].get(k) == v for k, v in where.items())
            ]

    def get_embeddings(self, chunk_ids: Sequence[str]) -> Dict[str, np.ndarray]:
        """
        按 chunk_id 批量取回库内向量（供 MMR 多样性重排等使用）。

        Returns:
            Dict[str, np.ndarray]: chunk_id → 归一化向量。
        """
        with self._lock:
            pos = {cid: i for i, cid in enumerate(self._ids)}
            out: Dict[str, np.ndarray] = {}
            for cid in chunk_ids:
                i = pos.get(cid)
                if i is not None and self._vectors.size:
                    out[cid] = self._vectors[i]
            return out

    def get_query_embedding(self, text: str) -> np.ndarray:
        """计算并返回归一化的查询向量（供 MMR 计算多样性用）。"""
        vec = np.asarray(self._embedder.embed_query(text), dtype=np.float32)
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

    def close(self) -> None:
        """关闭 SQLite 连接（应用关闭/测试清理时调用）。"""
        with self._lock:
            try:
                self._db.close()
            except Exception:  # noqa: BLE001
                pass
