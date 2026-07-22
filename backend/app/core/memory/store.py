"""
记忆存储层（SQLite）。

使用标准库 sqlite3 作为轻量持久化后端，无需额外服务，Docker 友好。
封装底层建表与连接管理，向上层（会话记忆、长期记忆）提供统一的数据访问。

数据表设计：
- sessions       会话元数据（ID、标题、时间戳）
- messages       多轮对话消息（归属会话，含角色、内容、时间）
- long_term      长期记忆条目（键值 + 主题标签 + 重要度 + 过期时间）
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)


class MemoryStore:
    """SQLite 记忆存储管理器（线程安全）。"""

    def __init__(self, db_path: str) -> None:
        """
        Args:
            db_path: SQLite 数据库文件路径。
        """
        self._db_path = db_path
        # sqlite3 连接非线程安全，用锁保护跨线程访问（FastAPI 线程池场景）
        self._lock = threading.Lock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False 允许在不同线程复用连接（配合锁使用）
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        logger.info("记忆库已连接: %s", db_path)

    def _init_schema(self) -> None:
        """初始化数据表（若不存在）。"""
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id          TEXT PRIMARY KEY,
                    title       TEXT NOT NULL,
                    created_at  REAL NOT NULL,
                    updated_at  REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id  TEXT NOT NULL,
                    role        TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    created_at  REAL NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                );

                CREATE TABLE IF NOT EXISTS long_term (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    key         TEXT NOT NULL,
                    value       TEXT NOT NULL,
                    topic       TEXT,
                    importance  INTEGER DEFAULT 1,
                    created_at  REAL NOT NULL,
                    expires_at  REAL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_session
                    ON messages(session_id);
                CREATE INDEX IF NOT EXISTS idx_long_term_topic
                    ON long_term(topic);
                """
            )
            self._conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """
        执行写操作（INSERT/UPDATE/DELETE）并提交。

        Args:
            sql: SQL 语句。
            params: 参数元组。

        Returns:
            sqlite3.Cursor: 执行后的游标（可取 lastrowid）。
        """
        with self._lock:
            cursor = self._conn.execute(sql, params)
            self._conn.commit()
            return cursor

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        """
        执行查询并返回全部结果行。

        Args:
            sql: SQL 查询语句。
            params: 参数元组。

        Returns:
            list[sqlite3.Row]: 结果行列表。
        """
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """执行查询并返回首行（无结果时返回 None）。"""
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def close(self) -> None:
        """关闭数据库连接。"""
        with self._lock:
            self._conn.close()
