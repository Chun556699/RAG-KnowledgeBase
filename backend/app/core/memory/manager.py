"""
上下文记忆管理器。

统一封装四类能力，对应需求中的「上下文记忆管理」模块：
1. 会话管理：创建/列出会话，维护多轮对话上下文连续性；
2. 短期记忆：读写单会话的历史消息，供构造 LLM 上下文；
3. 长期记忆：持久化用户偏好/重要事实，支持按主题检索；
4. 历史检索与清理：按时间/主题检索历史，自动清理过期记忆。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

from app.core.memory.store import MemoryStore
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ChatMessage:
    """单条对话消息。"""

    role: str
    content: str
    created_at: float = field(default_factory=time.time)


@dataclass
class SessionInfo:
    """会话元数据。"""

    id: str
    title: str
    created_at: float
    updated_at: float


@dataclass
class LongTermItem:
    """长期记忆条目。"""

    id: int
    key: str
    value: str
    topic: Optional[str]
    importance: int
    created_at: float
    expires_at: Optional[float]


class MemoryManager:
    """记忆管理器：会话、短期历史、长期记忆的统一门面。"""

    def __init__(
        self,
        store: MemoryStore,
        max_history_turns: int = 20,
        ttl_days: int = 30,
    ) -> None:
        """
        Args:
            store: 底层存储实例。
            max_history_turns: 构造上下文时保留的最大历史轮数。
            ttl_days: 长期记忆默认存活天数。
        """
        self._store = store
        self._max_history_turns = max_history_turns
        self._ttl_seconds = ttl_days * 86400

    # ------------------------------------------------------------------
    # 会话管理
    # ------------------------------------------------------------------
    def create_session(self, title: str = "新会话") -> SessionInfo:
        """创建新会话并返回其信息。"""
        session_id = uuid.uuid4().hex
        now = time.time()
        self._store.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (session_id, title, now, now),
        )
        logger.info("创建会话: %s", session_id)
        return SessionInfo(session_id, title, now, now)

    def list_sessions(self) -> List[SessionInfo]:
        """列出全部会话，按最近更新降序。"""
        rows = self._store.query(
            "SELECT id, title, created_at, updated_at FROM sessions ORDER BY updated_at DESC"
        )
        return [
            SessionInfo(r["id"], r["title"], r["created_at"], r["updated_at"])
            for r in rows
        ]

    def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """按 ID 获取会话，不存在返回 None。"""
        r = self._store.query_one(
            "SELECT id, title, created_at, updated_at FROM sessions WHERE id = ?",
            (session_id,),
        )
        if r is None:
            return None
        return SessionInfo(r["id"], r["title"], r["created_at"], r["updated_at"])

    def delete_session(self, session_id: str) -> None:
        """删除会话及其全部消息。"""
        self._store.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        self._store.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        logger.info("删除会话: %s", session_id)

    # ------------------------------------------------------------------
    # 短期记忆（会话消息）
    # ------------------------------------------------------------------
    def add_message(self, session_id: str, role: str, content: str) -> None:
        """向会话追加一条消息，并刷新会话更新时间。"""
        now = time.time()
        self._store.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, now),
        )
        self._store.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id)
        )

    def get_history(
        self, session_id: str, limit: Optional[int] = None
    ) -> List[ChatMessage]:
        """
        获取会话历史消息（按时间升序）。

        Args:
            session_id: 会话 ID。
            limit: 返回条数上限，默认使用 max_history_turns*2（一问一答算两条）。

        Returns:
            List[ChatMessage]: 历史消息列表。
        """
        cap = limit if limit is not None else self._max_history_turns * 2
        rows = self._store.query(
            "SELECT role, content, created_at FROM messages "
            "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, cap),
        )
        # 取出时为降序，反转为时间升序返回
        return [ChatMessage(r["role"], r["content"], r["created_at"]) for r in reversed(rows)]

    def search_history(
        self, keyword: str, limit: int = 20
    ) -> List[ChatMessage]:
        """
        跨会话按关键词检索历史消息（历史检索能力）。

        Args:
            keyword: 检索关键词。
            limit: 返回条数上限。

        Returns:
            List[ChatMessage]: 命中的历史消息，按时间降序。
        """
        rows = self._store.query(
            "SELECT role, content, created_at FROM messages "
            "WHERE content LIKE ? ORDER BY id DESC LIMIT ?",
            (f"%{keyword}%", limit),
        )
        return [ChatMessage(r["role"], r["content"], r["created_at"]) for r in rows]

    # ------------------------------------------------------------------
    # 长期记忆
    # ------------------------------------------------------------------
    def remember(
        self,
        key: str,
        value: str,
        topic: Optional[str] = None,
        importance: int = 1,
        ttl_seconds: Optional[int] = None,
    ) -> int:
        """
        写入一条长期记忆。

        Args:
            key: 记忆键（如「用户偏好语言」）。
            value: 记忆值。
            topic: 主题标签，便于分类检索。
            importance: 重要度（1~5），越高越优先保留。
            ttl_seconds: 存活秒数，None 使用默认 TTL。

        Returns:
            int: 新记录的自增 ID。
        """
        now = time.time()
        ttl = ttl_seconds if ttl_seconds is not None else self._ttl_seconds
        expires_at = now + ttl if ttl > 0 else None
        cursor = self._store.execute(
            "INSERT INTO long_term (key, value, topic, importance, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (key, value, topic, importance, now, expires_at),
        )
        return int(cursor.lastrowid)

    def recall(
        self, topic: Optional[str] = None, limit: int = 20
    ) -> List[LongTermItem]:
        """
        检索长期记忆（自动过滤已过期项）。

        Args:
            topic: 若指定，仅返回该主题的记忆。
            limit: 返回条数上限。

        Returns:
            List[LongTermItem]: 长期记忆列表，按重要度与时间排序。
        """
        now = time.time()
        if topic:
            rows = self._store.query(
                "SELECT * FROM long_term WHERE topic = ? AND (expires_at IS NULL OR expires_at > ?) "
                "ORDER BY importance DESC, created_at DESC LIMIT ?",
                (topic, now, limit),
            )
        else:
            rows = self._store.query(
                "SELECT * FROM long_term WHERE (expires_at IS NULL OR expires_at > ?) "
                "ORDER BY importance DESC, created_at DESC LIMIT ?",
                (now, limit),
            )
        return [
            LongTermItem(
                r["id"], r["key"], r["value"], r["topic"],
                r["importance"], r["created_at"], r["expires_at"],
            )
            for r in rows
        ]

    def cleanup_expired(self) -> int:
        """
        清理已过期的长期记忆（记忆清理能力）。

        Returns:
            int: 被清理的条目数。
        """
        now = time.time()
        cursor = self._store.execute(
            "DELETE FROM long_term WHERE expires_at IS NOT NULL AND expires_at <= ?",
            (now,),
        )
        deleted = cursor.rowcount
        if deleted:
            logger.info("清理过期长期记忆 %d 条", deleted)
        return deleted
