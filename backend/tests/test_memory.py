"""
记忆管理测试。

覆盖会话生命周期、多轮消息、历史检索、长期记忆读写与过期清理（TTL）。
使用临时 SQLite 数据库（memory_manager 夹具），互不干扰。
"""

from __future__ import annotations

import time


def test_session_lifecycle(memory_manager):
    """创建 -> 查询 -> 删除会话的完整生命周期。"""
    session = memory_manager.create_session("测试会话")
    assert session.title == "测试会话"

    fetched = memory_manager.get_session(session.id)
    assert fetched is not None and fetched.id == session.id

    assert len(memory_manager.list_sessions()) == 1

    memory_manager.delete_session(session.id)
    assert memory_manager.get_session(session.id) is None
    assert memory_manager.list_sessions() == []


def test_message_history_order(memory_manager):
    """历史消息应按时间升序返回。"""
    s = memory_manager.create_session()
    memory_manager.add_message(s.id, "user", "第一条")
    memory_manager.add_message(s.id, "assistant", "第二条")
    memory_manager.add_message(s.id, "user", "第三条")

    history = memory_manager.get_history(s.id)
    assert [m.content for m in history] == ["第一条", "第二条", "第三条"]
    assert history[0].role == "user"


def test_history_limit(memory_manager):
    """limit 参数应限制返回的最近条数。"""
    s = memory_manager.create_session()
    for i in range(10):
        memory_manager.add_message(s.id, "user", f"消息{i}")
    recent = memory_manager.get_history(s.id, limit=3)
    assert len(recent) == 3
    # 仍保持升序，取的是最近 3 条
    assert [m.content for m in recent] == ["消息7", "消息8", "消息9"]


def test_search_history(memory_manager):
    """跨会话按关键词检索历史消息。"""
    s1 = memory_manager.create_session()
    s2 = memory_manager.create_session()
    memory_manager.add_message(s1.id, "user", "如何实现向量检索")
    memory_manager.add_message(s2.id, "user", "今天天气不错")

    hits = memory_manager.search_history("向量检索")
    assert len(hits) == 1
    assert "向量检索" in hits[0].content


def test_long_term_remember_and_recall(memory_manager):
    """长期记忆写入后应可按主题召回。"""
    memory_manager.remember("语言偏好", "中文", topic="偏好", importance=5)
    memory_manager.remember("城市", "上海", topic="档案", importance=3)

    all_items = memory_manager.recall()
    assert len(all_items) == 2
    # 按重要度降序，偏好在前
    assert all_items[0].key == "语言偏好"

    only_pref = memory_manager.recall(topic="偏好")
    assert len(only_pref) == 1
    assert only_pref[0].value == "中文"


def test_cleanup_expired(memory_manager):
    """过期的长期记忆应被清理，未过期的保留。"""
    # 极短 TTL，稍后即过期（expires_at = now + 0.01）
    memory_manager.remember("临时", "将过期", ttl_seconds=0.01)
    # 永久（ttl<=0 时 expires_at 为 None，不过期）
    memory_manager.remember("永久", "保留", ttl_seconds=0)

    time.sleep(0.05)
    deleted = memory_manager.cleanup_expired()
    assert deleted == 1

    remaining = memory_manager.recall()
    assert len(remaining) == 1
    assert remaining[0].key == "永久"
