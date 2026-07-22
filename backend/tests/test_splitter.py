"""
文本分块模块测试。

验证分块的大小约束、重叠、边界条件与参数校验。
"""

from __future__ import annotations

import pytest

from app.core.rag.splitter import Chunk, TextSplitter


def test_empty_text_returns_no_chunks():
    """空文本应返回空列表。"""
    splitter = TextSplitter(chunk_size=100, chunk_overlap=10)
    assert splitter.split("") == []
    assert splitter.split("   ") == []


def test_short_text_single_chunk():
    """短于 chunk_size 的文本应只产生一个块。"""
    splitter = TextSplitter(chunk_size=100, chunk_overlap=10)
    chunks = splitter.split("这是一段很短的文本。")
    assert len(chunks) == 1
    assert isinstance(chunks[0], Chunk)
    assert chunks[0].index == 0


def test_long_text_multiple_chunks():
    """长文本应被切分为多个块，每块大小受控（含重叠冗余）。"""
    text = "。".join(f"这是第{i}个句子" for i in range(200))
    splitter = TextSplitter(chunk_size=100, chunk_overlap=20)
    chunks = splitter.split(text)
    assert len(chunks) > 1
    # 合并时会为下一块附加至多 chunk_overlap 的重叠，故上界为 size + overlap
    for c in chunks:
        assert len(c.text) <= 100 + 20


def test_chunk_indices_are_sequential():
    """块序号应从 0 起连续递增。"""
    text = "段落。" * 300
    splitter = TextSplitter(chunk_size=80, chunk_overlap=10)
    chunks = splitter.split(text)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_invalid_overlap_raises():
    """overlap >= chunk_size 应抛出 ValueError。"""
    with pytest.raises(ValueError):
        TextSplitter(chunk_size=50, chunk_overlap=50)
    with pytest.raises(ValueError):
        TextSplitter(chunk_size=50, chunk_overlap=100)
