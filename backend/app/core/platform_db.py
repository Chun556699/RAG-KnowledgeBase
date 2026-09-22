"""
平台数据库模块（企业化基座）。

用一个轻量 SQLite 库承载两类多租户数据：
1. **知识库（Knowledge Base）注册表**：每个接入产品/业务线对应一个 KB，
   文档、片段、检索均以 kb_id 隔离；
2. **API 密钥**：供外部产品调用公开问答 API 的凭证，
   仅存 SHA-256 散列（明文只在创建时返回一次），按 scope 授权、
   可绑定到具体知识库（tenant 隔离），可随时吊销。

密钥格式：``ak_live_<40 hex>``，列表/日志仅展示 ``ak_live_ab12…`` 前缀。
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_bases (
    kb_id       TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS api_keys (
    key_id      TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    key_hash    TEXT NOT NULL UNIQUE,
    key_prefix  TEXT NOT NULL,
    scopes      TEXT NOT NULL DEFAULT 'ask',   -- 逗号分隔: ask / ingest / admin
    kb_id       TEXT,                           -- NULL 表示不绑定（全部知识库）
    created_at  REAL NOT NULL,
    last_used_at REAL,
    revoked     INTEGER NOT NULL DEFAULT 0
);
"""

KEY_PREFIX = "ak_live_"


@dataclass
class ApiKeyInfo:
    """已验证的 API Key 信息（鉴权结果）。"""

    key_id: str
    name: str
    scopes: List[str]
    kb_id: Optional[str]  # None = 不限定知识库


@dataclass
class ApiKeyRecord:
    """API Key 的管理视图（脱敏，不含散列之外的任何密钥材料）。"""

    key_id: str
    name: str
    key_prefix: str
    scopes: List[str]
    kb_id: Optional[str]
    created_at: float
    last_used_at: Optional[float]
    revoked: bool


@dataclass
class KnowledgeBase:
    """知识库记录。"""

    kb_id: str
    name: str
    description: str
    created_at: float


class PlatformDB:
    """平台库：知识库注册表 + API 密钥的持久化与校验。"""

    def __init__(self, db_path: str) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(self._path), check_same_thread=False)
        self._db.executescript(_SCHEMA)
        with self._db:
            # 保证默认知识库始终存在（旧数据 kb_id 均为 default）
            self._db.execute(
                "INSERT OR IGNORE INTO knowledge_bases(kb_id, name, description, created_at)"
                " VALUES ('default', '默认知识库', '系统内置知识库', ?)",
                (time.time(),),
            )

    # ------------------------------------------------------------------
    # 知识库
    # ------------------------------------------------------------------
    def create_kb(self, name: str, description: str = "") -> KnowledgeBase:
        """创建知识库，返回记录。"""
        kb_id = "kb_" + secrets.token_hex(8)
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO knowledge_bases(kb_id, name, description, created_at)"
                " VALUES (?, ?, ?, ?)",
                (kb_id, name.strip() or kb_id, description.strip(), time.time()),
            )
        logger.info("创建知识库 %s (%s)", name, kb_id)
        return KnowledgeBase(kb_id=kb_id, name=name, description=description, created_at=time.time())

    def list_kbs(self) -> List[KnowledgeBase]:
        """列出全部知识库。"""
        with self._lock:
            rows = self._db.execute(
                "SELECT kb_id, name, description, created_at FROM knowledge_bases ORDER BY created_at"
            ).fetchall()
        return [
            KnowledgeBase(kb_id=r[0], name=r[1], description=r[2], created_at=r[3])
            for r in rows
        ]

    def get_kb(self, kb_id: str) -> Optional[KnowledgeBase]:
        """按 ID 取知识库。"""
        with self._lock:
            r = self._db.execute(
                "SELECT kb_id, name, description, created_at FROM knowledge_bases WHERE kb_id = ?",
                (kb_id,),
            ).fetchone()
        return KnowledgeBase(r[0], r[1], r[2], r[3]) if r else None

    # ------------------------------------------------------------------
    # API 密钥
    # ------------------------------------------------------------------
    @staticmethod
    def _hash(raw_key: str) -> str:
        """对明文密钥做 SHA-256 散列（只存散列，不落明文）。"""
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def create_key(
        self,
        name: str,
        scopes: Optional[List[str]] = None,
        kb_id: Optional[str] = None,
    ) -> tuple[ApiKeyRecord, str]:
        """
        创建 API Key。

        Returns:
            (ApiKeyRecord, raw_key): 记录与**仅此一次返回**的明文密钥。
        """
        raw = KEY_PREFIX + secrets.token_hex(20)
        record = ApiKeyRecord(
            key_id="key_" + secrets.token_hex(8),
            name=name.strip() or "未命名密钥",
            key_prefix=raw[:14] + "…",
            scopes=sorted(set(scopes or ["ask"])),
            kb_id=kb_id,
            created_at=time.time(),
            last_used_at=None,
            revoked=False,
        )
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO api_keys(key_id, name, key_hash, key_prefix, scopes, kb_id, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    record.key_id,
                    record.name,
                    self._hash(raw),
                    record.key_prefix,
                    ",".join(record.scopes),
                    kb_id,
                    record.created_at,
                ),
            )
        logger.info("创建 API Key %s（scope=%s, kb=%s）", record.key_prefix, record.scopes, kb_id)
        return record, raw

    def verify_key(self, raw_key: str) -> Optional[ApiKeyInfo]:
        """
        校验明文密钥：命中且未吊销则返回授权信息，并刷新 last_used_at。

        Args:
            raw_key: 请求携带的明文密钥（X-API-Key 或 Bearer）。

        Returns:
            Optional[ApiKeyInfo]: 无效/吊销返回 None。
        """
        if not raw_key:
            return None
        digest = self._hash(raw_key.strip())
        with self._lock:
            r = self._db.execute(
                "SELECT key_id, name, scopes, kb_id FROM api_keys"
                " WHERE key_hash = ? AND revoked = 0",
                (digest,),
            ).fetchone()
            if r is None:
                return None
            self._db.execute(
                "UPDATE api_keys SET last_used_at = ? WHERE key_id = ?",
                (time.time(), r[0]),
            )
            self._db.commit()
        return ApiKeyInfo(
            key_id=r[0],
            name=r[1],
            scopes=[s for s in r[2].split(",") if s],
            kb_id=r[3],
        )

    def list_keys(self) -> List[ApiKeyRecord]:
        """列出全部密钥（仅前缀脱敏展示，绝不含明文/散列）。"""
        with self._lock:
            rows = self._db.execute(
                "SELECT key_id, name, key_prefix, scopes, kb_id, created_at, last_used_at, revoked"
                " FROM api_keys ORDER BY created_at DESC"
            ).fetchall()
        return [
            ApiKeyRecord(
                key_id=r[0],
                name=r[1],
                key_prefix=r[2],
                scopes=[s for s in r[3].split(",") if s],
                kb_id=r[4],
                created_at=r[5],
                last_used_at=r[6],
                revoked=bool(r[7]),
            )
            for r in rows
        ]

    def revoke_key(self, key_id: str) -> bool:
        """吊销密钥（软删除，保留审计记录）。"""
        with self._lock, self._db:
            cur = self._db.execute(
                "UPDATE api_keys SET revoked = 1 WHERE key_id = ?", (key_id,)
            )
        return cur.rowcount > 0

    def close(self) -> None:
        """关闭连接。"""
        with self._lock:
            try:
                self._db.close()
            except Exception:  # noqa: BLE001
                pass
